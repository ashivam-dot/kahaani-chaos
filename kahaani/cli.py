"""python -m kahaani.cli plan --out DIR [--dry] [--replay story.json] | render --plan DIR --art DIR --out DIR [--dry]
| publish | next | health

plan picks the next premise, writes and gates the story, and writes one image prompt per beat for the paint jobs.
render screens the paintings, narrates, renders, and (unless --dry) stores the finished Short as a draft release and
adds it to the ready buffer. publish fills the next slot from the oldest ready Short. Dry runs never touch the ledger
or YouTube; a replay re-renders a reviewed story without any text-model call, and outside a dry run publishes it
once, never when its story or premise was already made.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import config, gate, ledger, look, slots
from .spec import Beat, Story

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
log = logging.getLogger("kahaani")


def _outputs(**values) -> None:
    """Step outputs for the workflow (no-op outside Actions)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in values.items())


def summary(story: Story) -> dict:
    return {"id": story.id, "premise": story.premise, "title": story.title, "subgenre": story.subgenre,
            "motifs": story.motifs, "ending": story.ending, "opening": story.opening, "made_at": ledger.now()}


def story_from(draft: dict, premise: dict, story_id: str, writer: dict) -> Story:
    return Story(id=story_id, premise=premise["id"], title=draft["title"], hook=draft["hook"],
                 beats=[Beat(text=b["text"], scene=b["scene"], people=b["people"]) for b in draft["beats"]],
                 cast=draft["cast"], subgenre=draft["subgenre"], ending=draft["ending"], twist_beat=draft["twist_beat"],
                 description=draft["description"], motifs=premise["motifs"], hashtags=draft["hashtags"], writer=writer)


def art_plan(story: Story) -> dict:
    from . import imagegen

    return {"story": story.id, "model": "zimage", "steps": imagegen.MODELS["zimage"]["steps"],
            "width": imagegen.WIDTH, "height": imagegen.HEIGHT,
            "beats": look.plan(story.id, [asdict(b) for b in story.beats], story.cast)}


def plan(out: Path, dry: bool = False, replay: Path | None = None) -> dict:
    """story.json, art-plan.json and status.json in out; status says whether to paint, or why not."""
    from . import premises, voice, writer

    out.mkdir(parents=True, exist_ok=True)
    status: dict = {"at": ledger.now(), "dry": dry, "paint": False}
    try:
        history = ledger.history()
        if replay:
            story = Story.load(replay)
            if not dry:
                if slots.buffer_full(ledger.ready()):
                    status["skip"] = f"buffer full ({len(ledger.ready())} ready)"
                    return status
                if any(r.get("id") == story.id or r.get("premise") == story.premise for r in history):
                    raise ValueError(f"replay {story.id} (premise {story.premise}) was already made for the channel")
            problems = gate.check(asdict(story), {"subgenre": story.subgenre}, history, rotation=not dry)
            if problems:
                raise ValueError("replay fails the gates: " + "; ".join(problems))
        else:
            if not dry and slots.buffer_full(ledger.ready()):
                status["skip"] = f"buffer full ({len(ledger.ready())} ready)"
                return status
            if reason := voice.ready():
                status["held"] = reason
                return status
            with writer.Pen() as pen:
                if not dry:
                    try:
                        premises.refill(history, pen.chat)
                    except Exception as exc:  # a refill failing must not stop today's Short
                        status["refill"] = f"{type(exc).__name__}: {exc}"[:300]
                premise = premises.select(history)
                status["premise"] = premise["id"]
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
                draft, notes = writer.write(premise, history, pen.chat)
                story = story_from(draft, premise, f"kc-{stamp}-{premise['id']}", {"models": pen.used, "log": notes})
        story.save(out / "story.json")
        (out / "art-plan.json").write_text(json.dumps(art_plan(story), indent=1, ensure_ascii=False), encoding="utf-8")
        status.update(paint=True, story=story.id, premise=story.premise, beats=len(story.beats))
        return status
    except (premises.NoPremise, writer.WriterHold) as exc:
        status["held"] = (str(exc) if str(exc).startswith("hold:") else f"hold: {exc}")[:500]
        return status
    except Exception as exc:
        status.update(error=f"{type(exc).__name__}: {exc}"[:500], trace=traceback.format_exc()[-2000:])
        return status
    finally:
        (out / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False), encoding="utf-8")
        _outputs(paint=str(status["paint"]).lower(),
                 chunks=json.dumps([str(i) for i in range(status.get("beats", 0))]))


def _cast_text(story: Story) -> str:
    return "; ".join(f"{c['name']}: {c['look']}" for c in story.cast)


def render(plan_dir: Path, art_dir: Path | None, out: Path, dry: bool = False) -> dict:
    """Make the planned Short; unless dry, store it as a draft release and add it to the ready buffer."""
    from . import aiart, compose, gemini, store, voice

    health = {"at": ledger.now(), "ok": True, "dry": dry, "steps": []}
    status = json.loads((plan_dir / "status.json").read_text(encoding="utf-8")) \
        if (plan_dir / "status.json").exists() else {"error": "the plan job left no status"}
    premise = status.get("premise")
    try:
        if not dry:
            ledger.set_identity()
        if status.get("refill"):
            health["steps"].append(f"premise refill: {status['refill']}")
        if status.get("skip"):
            health["steps"].append(f"skip: {status['skip']}")
            return health
        if status.get("held"):
            raise RuntimeError(status["held"])
        if status.get("error") or not status.get("paint"):
            raise RuntimeError(f"plan failed: {status.get('error') or 'no story'}")
        story = Story.load(plan_dir / "story.json")
        work = out / story.id
        work.mkdir(parents=True, exist_ok=True)
        story.save(work / "story.json")
        problems = gate.check(asdict(story), {"subgenre": story.subgenre}, ledger.history(), rotation=not dry)
        if problems:
            raise RuntimeError("hold: the planned story fails the gates: " + "; ".join(problems))
        found = aiart.collect(art_dir, story.id, len(story.beats))
        health["steps"].append(f"paintings: {len(found)} of {len(story.beats)} made")
        report: list[dict] = []
        try:
            pictures = aiart.pictures(found, [b.text for b in story.beats], work / "pics",
                                      f"{story.title} — {story.description}", _cast_text(story), gemini.look, report)
        except gemini.Unavailable as exc:
            raise RuntimeError(f"hold: no model can check the paintings ({exc})") from exc
        finally:
            (work / "pictures.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        timing = voice.synthesize(story, work)
        stats = compose.render(story, timing, pictures, work)
        stats["voice"] = {k: timing["voice"].get(k) for k in ("engine", "identity", "served_model", "wpm", "coverage",
                                                              "tempo")}
        (work / "render.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
        health["made"] = {"id": story.id, "title": story.title, "duration": stats["duration"],
                          "voice": stats["voice"]["engine"], "wpm": stats["voice"]["wpm"]}
        if dry:
            health["steps"].append(f"dry run: made {story.id} ({stats['duration']} s), not stored or published")
            return health
        refused = gate.voice_ok(timing["voice"])
        if refused:
            raise RuntimeError(refused)
        tag = store.put(story.id, work, story.title)
        ledger.add_ready({**summary(story), "tag": tag, "voice": timing["voice"]["engine"]})
        health["steps"].append(f"ready: {story.id} stored as release {tag} ({len(ledger.ready())} ready)")
        return health
    except Exception as exc:
        reason = str(exc)
        if reason.startswith("hold:") or isinstance(exc, (aiart.PictureHold, voice.VoiceHold)):
            health["held"] = reason[:500]
        else:
            health.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:500], trace=traceback.format_exc()[-2000:])
        if premise and not dry and not reason.startswith("hold: no narrator voice"):
            ledger.retry(premise, reason)
        health["steps"].append(f"{'hold' if health.get('held') else 'fail'} {premise or ''}: {reason}"[:400])
        return health
    finally:
        _save_health("produce", health, dry)


def _save_health(kind: str, health: dict, dry: bool) -> None:
    if dry:
        WORK.mkdir(parents=True, exist_ok=True)
        (WORK / f"dry-{kind}-health.json").write_text(json.dumps(health, indent=1, ensure_ascii=False),
                                                     encoding="utf-8")
    else:
        ledger.save_health(kind, health)


def publish(now: datetime | None = None, api=None) -> dict:
    """Fill the slot that is due from the oldest ready Short, then delete its release."""
    from . import learn, store, youtube

    now = now or datetime.now(timezone.utc)
    health = {"at": ledger.now(), "ok": True, "steps": []}
    try:
        ledger.set_identity()
        if not config.channel_id_ready():
            health["held"] = "hold: KC_CHANNEL_ID is not set"
            return health
        try:
            learned = learn.refresh(api=api)
            if learned is not None:
                health["steps"].append(f"learn: {learned['scored']} scored Shorts, lifts {learned['lifts']}"[:400])
        except Exception as exc:  # the numbers steer selection; reading them must never stop a publish
            health["steps"].append(f"learn: {type(exc).__name__}: {exc}"[:300])
        for row in [r for r in ledger.published() if r.get("release_left")]:
            try:
                store.drop(row["id"])
                ledger.mark(row["id"], release_left=False)
            except Exception as exc:
                health["steps"].append(f"release of {row['id']} still not deleted: {exc}"[:300])
        due = slots.due(now, slots.taken(ledger.published()))
        if due is None:
            health["steps"].append("the next slot is already filled")
            return health
        ready = ledger.ready()
        if not ready:
            health["held"] = f"hold: the buffer is empty; slot {due['slot']} has no Short"
            return health
        row = ready[0]
        folder = WORK / "publish" / row["id"]
        store.fetch(row["id"], folder)
        story = Story.load(folder / "story.json")
        voice = json.loads((folder / "timing.json").read_text(encoding="utf-8"))["voice"]
        result = youtube.publish(story, folder / "short.mp4", voice, publish_at=due["publish_at"], api=api)
        entry = {**row, "slot": due["slot"], "published_at": due["publish_at"] or ledger.now(), **result}
        ledger.record_publish(entry)
        health["steps"].append(f"{result['privacy']} {row['id']} for {due['slot']}: {result['url']}")
        health["published"] = result
        try:
            store.drop(row["id"])
        except Exception as exc:
            ledger.mark(row["id"], release_left=True)
            health["steps"].append(f"release of {row['id']} not deleted yet: {exc}"[:300])
        shutil.rmtree(folder, ignore_errors=True)
        return health
    except Exception as exc:
        health.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:500], trace=traceback.format_exc()[-2000:])
        return health
    finally:
        ledger.save_health("publish", health)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    p = argparse.ArgumentParser(prog="kahaani")
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--out", type=Path, required=True)
    pl.add_argument("--dry", action="store_true")
    pl.add_argument("--replay", type=Path)
    r = sub.add_parser("render")
    r.add_argument("--plan", type=Path, required=True)
    r.add_argument("--art", type=Path)
    r.add_argument("--out", type=Path, default=WORK)
    r.add_argument("--dry", action="store_true")
    sub.add_parser("publish")
    sub.add_parser("next")
    sub.add_parser("health")
    a = p.parse_args(argv)
    if a.cmd == "plan":
        status = plan(a.out, dry=a.dry, replay=a.replay)
        print(json.dumps({k: v for k, v in status.items() if k != "trace"}, indent=1, ensure_ascii=False))
        return 1 if status.get("error") else 0
    if a.cmd == "render":
        health = render(a.plan, a.art, a.out, dry=a.dry)
    elif a.cmd == "publish":
        health = publish()
    elif a.cmd == "next":
        from . import premises

        print(json.dumps(premises.select(ledger.history()), indent=1, ensure_ascii=False))
        return 0
    else:
        print(json.dumps(ledger.load("health", {}), indent=1, ensure_ascii=False))
        return 0
    print(json.dumps({k: v for k, v in health.items() if k != "trace"}, indent=1, ensure_ascii=False))
    return 0 if health["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
