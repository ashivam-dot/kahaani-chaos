"""What the channel's own numbers say, fed back into premise selection (PLAN.md §7.7).

Every REFRESH the publish run reads each published Short's views, likes and comments from the Data API and, when the
token has the yt-analytics.readonly scope, its average percentage viewed and subscribers gained from YouTube
Analytics. A Short is scored once it is SCORE_AT_H hours old: 0.5 x avg % viewed (z-score) + 0.3 x views (log,
z-score) + 0.2 x subscribers per 1K views (z-score), or the views term alone while Analytics is unavailable (the
health check then raises "analytics scope missing"). Each feature value (title skeleton, ending, resolution, heart
type, per format) gets a lift from its Shorts' mean score; selection ranks by it. A lift needs MIN_SAMPLES scored
Shorts, is shrunk toward 1 by n / (n + PRIOR) and stays within LIFT_RANGE, so a couple of lucky uploads cannot steer
the channel. Everything lands in state/performance.json, with a readable state/LEARNINGS.md.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from . import ledger

REFRESH = timedelta(hours=3)
SCORE_AT_H = 48.0
MIN_SAMPLES = 4
PRIOR = 4.0
LIFT_RANGE = (0.75, 1.35)
FEATURES = ("format", "skeleton", "ending", "resolution", "heart_type", "subgenre")
WEIGHTS = {"viewed_pct": 0.5, "views": 0.3, "subs_per_1k": 0.2}
LIFT_PER_Z = 0.3  # a feature whose Shorts score one standard deviation above the channel earns about x1.35
KEEP_SNAPSHOTS = 16


def _age_h(row: dict, at: datetime) -> float:
    return (at - datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))).total_seconds() / 3600


def views_at(snapshots: list[dict], hours: float) -> float | None:
    """Views at `hours` after publishing: interpolated between snapshots, or scaled back from the first later one
    (views grow roughly with the square root of age once a Short's first push is over). None while too young."""
    snaps = sorted(snapshots, key=lambda s: s["age_h"])
    if not snaps or snaps[-1]["age_h"] < hours:
        return None
    later = next(s for s in snaps if s["age_h"] >= hours)
    earlier = [s for s in snaps if s["age_h"] < hours]
    if not earlier:
        return later["views"] * math.sqrt(hours / later["age_h"]) if later["age_h"] > 0 else float(later["views"])
    a = earlier[-1]
    span = later["age_h"] - a["age_h"]
    return a["views"] + (later["views"] - a["views"]) * ((hours - a["age_h"]) / span if span else 1.0)


def _thin(snapshots: list[dict]) -> list[dict]:
    """Every snapshot until twice the scoring age (they set the score), then the newest few."""
    early = [s for s in snapshots if s["age_h"] <= 2 * SCORE_AT_H]
    late = [s for s in snapshots if s["age_h"] > 2 * SCORE_AT_H]
    return (early + late[-4:])[-KEEP_SNAPSHOTS:]


def _z(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0] * len(values)
    mean = sum(values) / len(values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))
    return [(v - mean) / sd if sd else 0.0 for v in values]


def scores(scored: list[dict]) -> list[float]:
    """The weighted score of each scored Short: the Analytics terms when every Short has them, else views alone."""
    views = _z([math.log1p(v["views_48h"]) for v in scored])
    if not all(v.get("viewed_pct") is not None and v.get("subs") is not None for v in scored):
        return views
    pct = _z([float(v["viewed_pct"]) for v in scored])
    subs = _z([1000.0 * v["subs"] / max(v["views_48h"], 1.0) for v in scored])
    return [WEIGHTS["viewed_pct"] * p + WEIGHTS["views"] * w + WEIGHTS["subs_per_1k"] * s
            for p, w, s in zip(pct, views, subs)]


def learn(videos: list[dict]) -> dict:
    scored = [v for v in videos if v.get("views_48h") is not None]
    out = {"scored": len(scored), "min_samples": MIN_SAMPLES, "lifts": {}}
    if len(scored) < MIN_SAMPLES:
        return out
    logs = [math.log1p(v["views_48h"]) for v in scored]
    out["baseline_views_48h"] = round(math.expm1(sum(logs) / len(logs)))
    full = all(v.get("viewed_pct") is not None and v.get("subs") is not None for v in scored)
    out["score"] = "0.5 viewed% + 0.3 views + 0.2 subs/1K (z)" if full else "views only (no Analytics)"
    for feature in FEATURES:
        groups: dict[str, list[float]] = {}
        for v, score in zip(scored, scores(scored)):
            if v.get(feature):
                groups.setdefault(str(v[feature]), []).append(score)
        for value, group in groups.items():
            n = len(group)
            if n < MIN_SAMPLES:
                continue
            mean = sum(group) / n
            lift = min(max(math.exp(LIFT_PER_Z * mean * n / (n + PRIOR)), LIFT_RANGE[0]), LIFT_RANGE[1])
            out["lifts"][f"{feature}:{value}"] = {"n": n, "lift": round(lift, 3), "mean_z": round(mean, 3)}
    return out


def lift(feature: str, value=None) -> float:
    """The learned multiplier for a feature value, e.g. lift("skeleton", "S2") (1.0 until there is evidence). One
    argument is the old sub-genre form."""
    if value is None:
        feature, value = "subgenre", feature
    lifts = (ledger.load("performance", {}).get("learned") or {}).get("lifts", {})
    got = lifts.get(f"{feature}:{value}", {}).get("lift", 1.0)
    return min(max(got, LIFT_RANGE[0]), LIFT_RANGE[1])


def analytics(client, ids: list[str], start: str, end: str) -> dict[str, dict]:
    """{video id: {viewed_pct, subs}} from YouTube Analytics (lifetime to date). Raises when the scope is missing."""
    if not ids or client is None:
        return {}
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        rep = client.reports().query(ids="channel==MINE", startDate=start, endDate=end,
                                     metrics="views,averageViewPercentage,subscribersGained", dimensions="video",
                                     filters="video==" + ",".join(ids[i:i + 50])).execute()
        for row in rep.get("rows") or []:
            out[row[0]] = {"viewed_pct": float(row[2]), "subs": int(row[3])}
    return out


def report(perf: dict) -> str:
    learned = perf.get("learned") or {}
    lines = ["# What this channel's own numbers say", "",
             f"Updated {perf.get('at')}. Scored Shorts (views at {SCORE_AT_H:.0f} h): {learned.get('scored', 0)}. "
             f"Score: {learned.get('score', 'n/a')}. Analytics: {perf.get('analytics', 'n/a')}. "
             f"A lift needs {MIN_SAMPLES} scored Shorts per value; it is shrunk toward 1 and kept within "
             f"{LIFT_RANGE[0]}-{LIFT_RANGE[1]}.", ""]
    if learned.get("baseline_views_48h") is not None:
        lines.append(f"Baseline: a typical Short has {learned['baseline_views_48h']} views at 48 h.")
    for key, v in sorted(learned.get("lifts", {}).items(), key=lambda kv: -kv[1]["lift"]):
        lines.append(f"- {key}: x{v['lift']} selection lift ({v['n']} Shorts, mean score {v['mean_z']:+})")
    if not learned.get("lifts"):
        lines.append("- No lift yet: not enough scored Shorts per value. Selection rotates on the bank order alone.")
    lines += ["", "| Short | published | format | skeleton | views now | views at 48 h | avg % viewed | subs |",
              "|---|---|---|---|---|---|---|---|"]
    for v in sorted(perf.get("videos", {}).values(), key=lambda v: v["published_at"], reverse=True)[:30]:
        now = v["snapshots"][-1]["views"] if v.get("snapshots") else ""
        at48 = "" if v.get("views_48h") is None else round(v["views_48h"])
        pct = "" if v.get("viewed_pct") is None else round(v["viewed_pct"], 1)
        lines.append(f"| {v['id']} | {v['published_at'][:16]} | {v.get('format') or ''} | {v.get('skeleton') or ''} "
                     f"| {now} | {at48} | {pct} | {v.get('subs', '')} |")
    return "\n".join(lines) + "\n"


def refresh(at: datetime | None = None, force: bool = False, api=None, analytics_api=None) -> dict | None:
    """Read the channel's numbers and relearn, at most once per REFRESH. Returns what was learned, or None if the
    last read is still fresh. performance.json's "analytics" says "ok" or why Analytics could not be read."""
    from . import youtube

    at = at or datetime.now(timezone.utc)
    perf = ledger.load("performance", {"at": None, "videos": {}})
    if not force and perf.get("at") and at - datetime.fromisoformat(perf["at"]) < REFRESH:
        return None
    if api is None:
        api = youtube.client()
    stats = {v["id"]: v.get("statistics", {}) for v in youtube.recent(api, youtube.identity(api))}
    for row in ledger.published():
        vid = row.get("video_id")
        if not vid or vid not in stats or _age_h(row, at) < 0:
            continue
        s = stats[vid]
        rec = perf["videos"].setdefault(vid, {"id": row["id"], "published_at": row["published_at"], "snapshots": []})
        rec.update({f: row.get(f) or rec.get(f) for f in FEATURES})
        rec["snapshots"] = _thin(rec["snapshots"] + [{
            "age_h": round(_age_h(row, at), 2), "views": int(s.get("viewCount", 0)),
            "likes": int(s.get("likeCount", 0)), "comments": int(s.get("commentCount", 0))}])
        rec["views_48h"] = views_at(rec["snapshots"], SCORE_AT_H)
    try:
        client = analytics_api if analytics_api is not None else youtube.analytics_client()
        first = min((r["published_at"][:10] for r in ledger.published() if r.get("published_at")), default=None)
        ids = [vid for vid, rec in perf["videos"].items() if rec.get("views_48h") is not None]
        numbers = analytics(client, ids, first or at.date().isoformat(), at.date().isoformat())
        for vid, got in numbers.items():
            perf["videos"][vid].update(got)
        perf["analytics"] = "ok"
    except Exception as exc:  # no yt-analytics.readonly scope, or Analytics lagging: views alone, and say so
        perf["analytics"] = f"missing: {type(exc).__name__}: {exc}"[:300]
    perf["at"] = at.isoformat(timespec="seconds")
    perf["learned"] = learn(list(perf["videos"].values()))
    ledger.save("performance", perf)
    (ledger.STATE / "LEARNINGS.md").write_text(report(perf), encoding="utf-8")
    return perf["learned"]
