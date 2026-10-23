"""The relaunched channel's look and About text: banner and avatar paintings, the composed banner, description and
keywords.

python -m kahaani.branding plan --out DIR             art plans for the banner and the avatar (kahaani.imagegen)
python -m kahaani.branding compose --art DIR --out DIR  banner-N.jpg (2560x1440, title in the safe area), avatar-N.jpg
python -m kahaani.branding apply --banner FILE [--write] description, keywords and banner, read back

The API cannot rename a channel or set its avatar; those two are done in Studio with the avatar made here. Paintings
follow the house style and carry no people, so no face or age can go wrong at banner size.
"""
from __future__ import annotations

import argparse
import json
import shlex
import time
import unicodedata
from pathlib import Path

from . import bible
from . import look
from .look import AVOID, NEVER, NOBODY

TITLE = "सन्नाटपुर की रातें"
TAGLINE = "1996 का एक काल्पनिक गाँव, और उसकी अजीब रातें"
DESCRIPTION = f"""{TITLE} | Sannatpur Ki Raatein

{TAGLINE}।

2026 में सैंतालीस साल का प्रभात याद करता है 1996 की वो रातें, जब वो सत्रह का था: बिना पैडल जलती साइकिल की बत्ती, आधी रात बजता ट्रांजिस्टर, PCO का मीटर जो अपने आप चलने लगा। गाँव का पहरेदार झब्बू चाचा हर अजीब रात का एक नियम अपने लाल रजिस्टर में लिखता है।

हर Short एक नई, पूरी कहानी: 90s की बिजली कटौती, लालटेन, कैसेट और अंतर्देशीय पत्रों के बीच छुपा एक रहस्य।

यह गाँव और इसकी कहानियाँ काल्पनिक हैं। चित्र AI से बने हैं और आवाज़ AI से बनी है।

#सन्नाटपुर #हिंदीकहानी #90s"""
KEYWORDS = ('सन्नाटपुर "सन्नाटपुर की रातें" "Sannatpur Ki Raatein" "हिंदी कहानी" "रहस्य कहानी" "गाँव की कहानी" '
            '"90s nostalgia" "hindi mystery" "hindi story" "village mystery" "1996"')

STYLE = (bible.house_style().rstrip(".") + ". Painterly visible brushwork, readable mid-tones, no crushed blacks."
         " Painterly-cinematic, not photoreal, not a cartoon.")
ART = {
    "banner": {"width": 1536, "height": 864, "seeds": [101, 202], "prompt": (
        "A wide, calm panorama of an invented 1996 north-Indian village at night under a big full moon: a brick canal"
        " bridge with a parked black bicycle whose dynamo headlight glows warm yellow, a hurricane lantern hung on a"
        " bamboo post, low mud-and-brick houses with one lit window, a concrete water tank, mist over the canal."
        " The middle band of the picture is open moonlit sky and soft mist, quiet and uncluttered; the details sit"
        " at the left and right edges and along the bottom.")},
    "avatar": {"width": 1024, "height": 1024, "seeds": [303, 404], "prompt": (
        "A brass hurricane lantern glowing warm orange, hung from a bamboo staff, centred in front of a big pale full"
        " moon in a deep blue night sky with a faint mist below. One bold, simple silhouette that reads clearly at a"
        " tiny size, nothing else in the picture.")},
}
SIZE = (2560, 1440)
SAFE = (1546, 423)  # the banner area every device shows, centred


def prompt(kind: str) -> str:
    return " ".join([ART[kind]["prompt"], NOBODY, STYLE, AVOID, NEVER])


def plans(out: Path) -> list[Path]:
    """One kahaani.imagegen prompts file per kind, each painted at its own size with every seed as a beat."""
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for kind, spec in ART.items():
        plan = {"story": f"branding-{kind}", "model": "zimage", "steps": 4, "width": spec["width"],
                "height": spec["height"], "beats": [{"prompt": prompt(kind), "seed": s} for s in spec["seeds"]]}
        path = out / f"{kind}-plan.json"
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        paths.append(path)
    return paths


def _text(draw, xy, text, font, fill, anchor="mm", shadow=6):
    x, y = xy
    for dx, dy in ((shadow, shadow), (0, shadow), (shadow, 0)):
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 170), anchor=anchor)
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def banner(painting: Path, out: Path) -> Path:
    """The painting at 2560x1440 with the title and tagline inside the centred safe area, on a soft dark band."""
    from PIL import Image, ImageDraw, ImageFilter

    from .compose import _font

    img = Image.open(painting).convert("RGB")
    scale = max(SIZE[0] / img.width, SIZE[1] / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - SIZE[0]) // 2, (img.height - SIZE[1]) // 2
    img = img.crop((left, top, left + SIZE[0], top + SIZE[1])).convert("RGBA")
    band = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    cx, cy = SIZE[0] // 2, SIZE[1] // 2
    ImageDraw.Draw(band).rounded_rectangle((cx - SAFE[0] // 2 + 60, cy - SAFE[1] // 2 + 20,
                                            cx + SAFE[0] // 2 - 60, cy + SAFE[1] // 2 - 20), 60, fill=(8, 12, 30, 120))
    img = Image.alpha_composite(img, band.filter(ImageFilter.GaussianBlur(40)))
    draw = ImageDraw.Draw(img)
    _text(draw, (cx, cy - 50), TITLE, _font("ExtraBold", 170), (255, 236, 196, 255))
    _text(draw, (cx, cy + 110), TAGLINE, _font("SemiBold", 62), (235, 228, 214, 255), shadow=4)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "JPEG", quality=92)
    return out


def avatar(painting: Path, out: Path) -> Path:
    from PIL import Image

    img = Image.open(painting).convert("RGB")
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img.crop((left, top, left + side, top + side)).resize((800, 800), Image.LANCZOS).save(out, "JPEG", quality=92)
    return out


def compose(art: Path, out: Path) -> list[Path]:
    made = []
    for kind, make in (("banner", banner), ("avatar", avatar)):
        for path in sorted(art.glob(f"{kind}/beat??.png")):  # named by seed slot, so a failed paint shifts nothing
            made.append(make(path, out / f"{kind}-{int(path.stem[4:])}.jpg"))
    return made


def _same(text: str | None) -> str:
    """Text as YouTube stores it: NFC, line ends and spaces per line normalised."""
    text = unicodedata.normalize("NFC", text or "").replace("\r\n", "\n")
    return "\n".join(line.rstrip() for line in text.strip().split("\n"))


def _tags(text: str | None) -> set[str]:
    """The keyword tags, however YouTube re-quotes them."""
    return {t.lower() for t in shlex.split(_same(text))}


# Sent back unchanged, these make channels.update answer 400 failedPrecondition (Pangaea Nights, 2026-10-23).
READ_ONLY = ("title", "unsubscribedTrailer")


def apply(api, banner_file: Path | None, write: bool) -> dict:
    from googleapiclient.http import MediaFileUpload

    from . import youtube

    me = youtube.identity(api)
    got = api.channels().list(part="brandingSettings", id=me["id"]).execute()["items"][0]["brandingSettings"]
    current = got.get("channel", {})
    wanted = {k: v for k, v in current.items() if k not in READ_ONLY} | {"description": DESCRIPTION,
                                                                          "keywords": KEYWORDS}
    out = {"channel": me["id"], "title_now": me["snippet"]["title"],
           "changed": sorted(k for k in ("description", "keywords") if wanted[k] != current.get(k)),
           "banner": str(banner_file) if banner_file else None, "write": write}
    if not write:
        return out
    body = {"id": me["id"], "brandingSettings": {"channel": wanted}}
    if banner_file:
        url = api.channelBanners().insert(media_body=MediaFileUpload(str(banner_file), mimetype="image/jpeg")) \
            .execute()["url"]
        body["brandingSettings"]["image"] = {"bannerExternalUrl": url}
    api.channels().update(part="brandingSettings", body=body).execute()
    for wait in (0, 5, 15, 30):  # the first read after an update can still show the old text
        time.sleep(wait)
        back = api.channels().list(part="brandingSettings", id=me["id"]).execute()["items"][0]["brandingSettings"]
        now = back.get("channel", {})
        off = [k for k, same in (("description", _same), ("keywords", _tags))
               if same(now.get(k)) != same(wanted[k])]
        if not off:
            break
    out["readback_ok"] = not off
    out["mismatch"] = {"description": {"sent": wanted["description"][:120], "read": (now.get("description") or "")[:120]}
                       if "description" in off else None,
                       "keywords": {"missing": sorted(_tags(wanted["keywords"]) - _tags(now.get("keywords"))),
                                    "extra": sorted(_tags(now.get("keywords")) - _tags(wanted["keywords"]))}
                       if "keywords" in off else None}
    out["banner_set"] = bool((back.get("image") or {}).get("bannerExternalUrl")) if banner_file else None
    if not out["readback_ok"] or out["banner_set"] is False:
        raise RuntimeError(f"branding read-back does not match: {json.dumps(out, ensure_ascii=False)[:1500]}")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kahaani.branding")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("plan").add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compose")
    c.add_argument("--art", type=Path, required=True)
    c.add_argument("--out", type=Path, required=True)
    a = sub.add_parser("apply")
    a.add_argument("--banner", type=Path)
    a.add_argument("--write", action="store_true")
    args = p.parse_args(argv)
    if args.command == "plan":
        print(json.dumps([str(x) for x in plans(args.out)]))
    elif args.command == "compose":
        print(json.dumps([str(x) for x in compose(args.art, args.out)]))
    else:
        from . import youtube

        print(json.dumps(apply(youtube.client(), args.banner, args.write), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
