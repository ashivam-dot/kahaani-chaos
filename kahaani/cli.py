"""python -m kahaani.cli plan --out DIR [--dry] [--replay story.json] | render --plan DIR --art DIR --out DIR [--dry]
| publish | next | health

plan picks the next F1 micro-entry from the bible's bank, writes and gates the story, and writes one image prompt per
beat (and spare seeds for cast shots) for the paint jobs. Hindi text written by the local fallback model is never
published: such a draft holds (PLAN.md §7.8).
render screens the paintings, narrates, renders, and (unless --dry) stores the finished Short as a draft release and
adds it to the ready buffer; a Short whose encoded runtime is outside the F1 band holds. publish fills the next slot
from the oldest ready Short (one found already public is recorded under the slot it went out in, and the next ready
Short fills the due one), and tries again the first comments and playlist adds YouTube refused. Dry runs never touch
the ledger
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
# A premise the editor keeps refusing used to cost the whole production slot (p013: 3 of 6 slots on 14-15 Oct).
PREMISES_PER_RUN = 3
# Holds that are the render's or a model's fault, not the premise's: the premise keeps its tries (the next run paints,
# narrates or renders it afresh).
NOT_THE_PREMISE = ("hold: no narrator voice", "hold: picture and sound checks", "hold: voice: ", "hold: prop identity")
# A first comment or playlist add YouTube refused is tried again on publish runs for this long after release.
PENDING_DAYS = 7
log = logging.getLogger("kahaani")


def _outputs(**values) -> None:
    """Step outputs for the workflow (no-op outside Actions)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in values.items())


def summary(story: Story) -> dict:
    """What the ledger keeps about a made Short (ledger.SUMMARY): what rotation and the variation gate compare."""
    return {"id": story.id, "premise": story.premise, "title": story.title, "subgenre": story.subgenre,
            "motifs": story.motifs, "ending": story.ending, "opening": story.opening, "made_at": ledger.now(),
            "format": story.format, "skeleton": story.skeleton, "resolution": story.resolution,
            "heart_type": story.heart_type, "object_token": story.object_token, "anomaly": story.anomaly,
            "location": story.location, "place_id": story.place_id, "hook_strip": story.hook_strip,
            "script": story.narration}


def story_from(draft: dict, premise: dict, story_id: str, writer: dict) -> Story:
    """A Story from a gated draft and its bank entry (premises.premise_for)."""
    return Story(id=story_id, premise=premise["id"], title=draft["title"], hook=draft["hook"],
                 beats=[Beat(text=b["text"], scene=b["scene"], people=b["people"]) for b in draft["beats"]],
                 cast=draft["cast"], subgenre=premise.get("heart_type", ""), ending=draft["ending"],
                 twist_beat=draft["twist_beat"], description=draft["description"], motifs=[],
                 hashtags=draft["hashtags"], writer=writer, format=config.FORMAT, hook_strip=draft["hook_strip"],
                 object_token=premise.get("object_token") or draft["object_token"], anomaly=premise.get("anomaly", ""),
                 niyam_id=draft["niyam_id"], resolution=draft["resolution"], heart_beat=draft["heart_beat"],
                 heart_type=premise.get("heart_type", ""), skeleton=premise.get("title_skeleton", ""),
                 location=premise.get("location", ""), place_id=premise.get("place_id", ""))


def premise_of(story: Story) -> dict:
    """The bank entry a made story came from, as the gates saw it (with the ending it was given)."""
    from . import premises

    entry = next((p for p in premises.bank() if p["id"] == story.premise), None)
    if entry is None:
        return {"id": story.premise, "ending_type": story.ending}
    return {**entry, "ending_type": story.ending}


LOCAL_HOLD = "hold: the draft came from the local fallback model; its Hindi is never published (wait for Gemini)"


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
            problems = gate.check(asdict(story), premise_of(story), history, rotation=not dry)
            if problems:
                raise ValueError("replay fails the gates: " + "; ".join(problems))
        else:
            if not dry and slots.buffer_full(ledger.ready()):
                status["skip"] = f"buffer full ({len(ledger.ready())} ready)"
                return status
            if reason := voice.ready():
                status["held"] = reason
                return status
            if low := premises.low(history):
                status["bank_low"] = low
            with writer.Pen() as pen:
                passed_over: list[list[str]] = []
                while True:
                    entry = premises.select(history, [p for p in premises.bank()
                                                      if p["id"] not in {q for q, _ in passed_over}])
                    premise = premises.premise_for(entry, history)
                    status["premise"] = premise["id"]
                    try:
                        draft, notes = writer.write(premise, history, pen.chat)
                        break
                    except writer.WriterHold as exc:
                        passed_over.append([premise["id"], str(exc)[:300]])
                        status["passed_over"] = passed_over
                        if len(passed_over) >= PREMISES_PER_RUN:
                            raise
                if not dry and any(not m.startswith("gemini") for m in pen.used):
                    raise writer.WriterHold(LOCAL_HOLD)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
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
    from . import aiart, compose, gemini, store, vision, voice

    health = {"at": ledger.now(), "ok": True, "dry": dry, "steps": []}
    status = json.loads((plan_dir / "status.json").read_text(encoding="utf-8")) \
        if (plan_dir / "status.json").exists() else {"error": "the plan job left no status"}
    premise = status.get("premise")
    try:
        if not dry:
            ledger.set_identity()
            for passed, why in status.get("passed_over", []):
                if passed != premise:
                    ledger.retry(passed, why)
        if status.get("bank_low"):
            health["bank_low"] = status["bank_low"]
            health["steps"].append(f"bank: {status['bank_low']}")
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
        problems = gate.check(asdict(story), premise_of(story), ledger.history(), rotation=not dry)
        if problems:
            raise RuntimeError("hold: the planned story fails the gates: " + "; ".join(problems))
        found = aiart.collect(art_dir, story.id, len(story.beats))
        spares = aiart.alternates(art_dir, story.id, len(story.beats))
        health["steps"].append(f"paintings: {len(found)} of {len(story.beats)} made, "
                               f"{sum(map(len, spares.values()))} repaints")
        who = {i: look.present([dict(p) for p in b.people], story.cast) for i, b in enumerate(story.beats)}
        report: list[dict] = []
        eye = vision.Eye()
        try:
            pictures = aiart.pictures(found, [b.text for b in story.beats], work / "pics",
                                      f"{story.title} — {story.description}", _cast_text(story), eye, report,
                                      spares=spares, who={i: w for i, w in who.items() if w},
                                      scenes=[b.scene for b in story.beats])
        except gemini.Unavailable as exc:
            raise RuntimeError(f"hold: no model can check the paintings ({exc})") from exc
        finally:
            eye.close()
            health["picture_editor"] = sorted(set(eye.used))
            (work / "pictures.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
        if not dry and not vision.LOCAL_TRUSTED and any(m != "gemini" for m in eye.used):
            raise aiart.PictureHold("hold: the local picture editor judged the paintings and is not calibrated yet "
                                    "(vision.LOCAL_TRUSTED; run the vision-bench workflow)")
        rate = aiart.prop_rate(report)
        if rate is not None:
            health["prop_identity"] = round(rate, 3)
            if rate < vision.PROP_RATE:
                raise aiart.PictureHold(f"hold: prop identity {rate:.0%} of cast shots, needs {vision.PROP_RATE:.0%}")
        timing = voice.synthesize(story, work)
        late = gate.timing_problems(story, timing)
        if late:
            raise voice.VoiceHold("hold: " + "; ".join(late))
        stats = compose.render(story, timing, pictures, work)
        runtime = gate.runtime_problems(stats.get("runtime"))
        if runtime:
            raise compose.ComposeHold("hold: picture and sound checks: " + "; ".join(runtime))
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
        # Neither a missing narrator, a Gemini outage nor a render or narration that missed its checks is the
        # premise's fault: it keeps its tries.
        if premise and not dry and not reason.startswith((*NOT_THE_PREMISE, LOCAL_HOLD)):
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
            seen = ledger.load("performance", {}).get("analytics") or ""
            if seen.startswith("missing"):
                health["analytics"] = seen  # the health check raises "analytics scope missing"
        except Exception as exc:  # the numbers steer selection; reading them must never stop a publish
            health["steps"].append(f"learn: {type(exc).__name__}: {exc}"[:300])
        for row in [r for r in ledger.published() if r.get("release_left")]:
            try:
                store.drop(row["id"])
                ledger.mark(row["id"], release_left=False)
            except Exception as exc:
                health["steps"].append(f"release of {row['id']} still not deleted: {exc}"[:300])
        api = _retry_pending(now, api, health)
        # Twice at most: a Short found already public takes the slot it went out in, and the next fills the due one.
        for _ in range(2):
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
            try:
                result = youtube.publish(story, folder / "short.mp4", voice, publish_at=due["publish_at"], api=api)
            except youtube.ReadbackMismatch as exc:
                health["readback"] = str(exc)[:500]
                raise
            for key in ("comment", "playlist"):
                if str(result.get(key, "")).startswith("pending"):
                    health["steps"].append(f"{key}: {result[key]}")
            if result.get("already_public"):
                slot = slots.slot_of(result["released_at"])
                slot = None if slot in slots.taken(ledger.published()) else slot
                ledger.record_publish({**row, "slot": slot, "published_at": result["released_at"], **result})
                health["steps"].append(f"{row['id']} was already public (since {result['released_at']}); recorded "
                                       f"for slot {slot}: {result['url']}")
                _drop_release(row["id"], folder, health)
                continue
            entry = {**row, "slot": due["slot"], "published_at": due["publish_at"] or ledger.now(), **result}
            ledger.record_publish(entry)
            health["steps"].append(f"{result['privacy']} {row['id']} for {due['slot']}: {result['url']}")
            health["published"] = result
            _drop_release(row["id"], folder, health)
            return health
        return health
    except Exception as exc:
        health.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:500], trace=traceback.format_exc()[-2000:])
        return health
    finally:
        ledger.save_health("publish", health)


def _drop_release(story_id: str, folder: Path, health: dict) -> None:
    from . import store

    try:
        store.drop(story_id)
    except Exception as exc:
        ledger.mark(story_id, release_left=True)
        health["steps"].append(f"release of {story_id} not deleted yet: {exc}"[:300])
    shutil.rmtree(folder, ignore_errors=True)


def _retry_pending(now: datetime, api, health: dict):
    """Try again the first comments and playlist adds YouTube refused (often: comments on a still-private video), for
    Shorts released less than PENDING_DAYS ago. Fails soft; returns the client it signed in with, if any."""
    from . import youtube

    def released(r: dict) -> datetime | None:
        try:
            return datetime.fromisoformat(str(r.get("published_at")).replace("Z", "+00:00"))
        except ValueError:
            return None

    rows = [r for r in ledger.published() if r.get("video_id") and (at := released(r)) and
            at <= now and (now - at).days < PENDING_DAYS and
            any(str(r.get(k, "")).startswith("pending") for k in ("comment", "playlist"))]
    if not rows:
        return api
    try:
        api = api or youtube.client()
        youtube.identity(api)
        for r in rows:
            fields = {}
            if str(r.get("comment", "")).startswith("pending"):
                fields["comment"] = youtube.first_comment(api, r["video_id"], r.get("comment_text") or youtube.CTA)
            if str(r.get("playlist", "")).startswith("pending"):
                fmt = config.FORMATS.get(r.get("format") or config.FORMAT, config.FORMATS[config.FORMAT])
                fields["playlist"] = youtube.add_to_playlist(api, r["video_id"], fmt.playlist_id)
            ledger.mark(r["id"], **fields)
            health["steps"].append(f"retried for {r['id']}: " + ", ".join(f"{k} {v}" for k, v in fields.items()))
    except Exception as exc:  # a comment never stops a publish
        health["steps"].append(f"pending comment or playlist: {type(exc).__name__}: {exc}"[:300])
    return api


def vision_bench(work: Path, out: Path) -> dict:
    """The local picture editor's verdicts on a finished run's paintings (work holds story.json, pics/beatNN.jpg and
    the Gemini editor's pictures.json), side by side with Gemini's, to calibrate vision.Eye before it may publish."""
    from . import vision

    story = Story.load(work / "story.json")
    who = {i: look.present([dict(p) for p in b.people], story.cast) for i, b in enumerate(story.beats)}
    shots = sorted((work / "pics").glob("beat??.jpg"))
    items = [(f, story.beats[int(f.stem[4:])].text, vision.expected(who.get(int(f.stem[4:]), [])),
              story.beats[int(f.stem[4:])].scene) for f in shots]
    gemini_rows = {r["beat"]: r for r in json.loads((work / "pictures.json").read_text(encoding="utf-8"))} \
        if (work / "pictures.json").exists() else {}
    with vision.Eye() as eye:
        eye.gemini_down = True
        verdicts = vision.judge(items, f"{story.title} — {story.description}", _cast_text(story), eye)
    rows = []
    for f, v in zip(shots, verdicts):
        i = int(f.stem[4:])
        g = gemini_rows.get(i + 1, {})
        rows.append({"beat": i + 1, "local_shows": v.get("shows"),
                     "local_rejected": vision.rejected(v, bool(who.get(i)), i == 0),
                     "gemini_shows": g.get("shows"),
                     "gemini_rejected": vision.rejected({"shows": g.get("shows"), "fits": True, "props_ok": True,
                                                         "subject_share": 0.5}, bool(who.get(i)), False)
                     if g else None, "local": v})
    out.mkdir(parents=True, exist_ok=True)
    report = {"model": eye.used[:1], "rows": rows}
    (out / "vision-bench.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return report


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
    vb = sub.add_parser("vision-bench")
    vb.add_argument("--work", type=Path, required=True)
    vb.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    if a.cmd == "vision-bench":
        print(json.dumps(vision_bench(a.work, a.out), indent=1, ensure_ascii=False))
        return 0
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

        history = ledger.history()
        print(json.dumps(premises.premise_for(premises.select(history), history), indent=1, ensure_ascii=False))
        return 0
    else:
        print(json.dumps(ledger.load("health", {}), indent=1, ensure_ascii=False))
        return 0
    print(json.dumps({k: v for k, v in health.items() if k != "trace"}, indent=1, ensure_ascii=False))
    return 0 if health["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
