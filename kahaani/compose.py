"""Story renderer: one AI painting per beat brought to life with depth parallax (a slow camera move through the
scene), a moonlit teal-and-amber grade, word-by-word Hindi captions, an always-visible AI and fiction label, an ending
card per ending type and a loudness-normalised mix over the dark-ambient bed. Pure Python + ffmpeg, about real time.

F1 layout (PLAN.md §5, §7.4 gates g and k): frame 0 is the peak image under a 3-5 word hook strip in the top third
(10-28% of the frame's height); captions sit above 75% of the height; nothing is drawn in the bottom 25% or the
right 12% (the Shorts player's buttons); the AI label is small in the top-left corner. The finished Short is held
unless frame 0's mean luma is 90-170 and its RMS contrast 0.18-0.45, no frame-to-frame luma drop above 35% happens
outside a cut, and the encoded file has the expected frame count (within one). Where the text lands is measured on
the frames themselves, not taken from the layout: the overlays are drawn once more on a black and a white canvas, and
any pixel they change is ink. Frame 0's hook strip must be 10-28% of the height and end inside the top third, and no
checked frame has ink below 75% of the height or in the right 12%. The music bed under the voice is measured too
(gate j's ceiling, MUSIC_BED).

Devanagari needs complex text shaping (conjuncts such as क्ष and त्र, vowel signs that sit before their consonant), so
every string is laid out with Pillow's RAQM engine (HarfBuzz + FriBiDi) in Mukta (SIL Open Font License, bundled in
kahaani/fonts). Pillow's basic layout draws Hindi wrongly, so rendering refuses to run without RAQM.
"""
from __future__ import annotations

import functools
import json
import math
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

from . import config, depth, gate, hindi, music
from .spec import Story

W, H, FPS = 1080, 1920, 30
MARGIN = 1.16  # the plate is larger than the frame so the camera can move
FONTS = Path(__file__).resolve().parent / "fonts"
WEIGHTS = {"ExtraBold": "Mukta-ExtraBold.ttf", "Bold": "Mukta-Bold.ttf", "SemiBold": "Mukta-SemiBold.ttf",
           "Medium": "Mukta-Medium.ttf"}
# On screen for the whole Short (India's IT Rules ask synthetic content to carry a visible label).
AI_LABEL = "AI चित्र और आवाज़ · काल्पनिक कहानी"
END_LINE = "यह कहानी काल्पनिक है · चित्र और आवाज़: AI"
ACCENT = (255, 190, 92)
CROSSFADE = 10  # frames
CAPTION_Y = 0.665
END_CARD = gate.END_CARD  # seconds after the narration
# Where text may go: above SAFE_BOTTOM of the height, left of SAFE_RIGHT of the width, SIDE pixels from the left edge.
SAFE_BOTTOM, SAFE_RIGHT, SIDE = 0.75, 0.88, 48
TEXT_W = round(W * SAFE_RIGHT) - 2 * SIDE
TEXT_CX = (SIDE + round(W * SAFE_RIGHT)) // 2
STRIP_TOP = 0.05
STRIP_SHARE = (0.10, 0.28)  # the hook strip's share of the frame height
VIGNETTE_FLOOR = 0.65
LIFT = 14.0  # shadows lifted by this much (8-bit): moonlit, never crushed to black
EXPOSURE = (118.0, 0.85, 1.35)  # each painting is nudged toward this mean luma, by a gain within these bounds
FRAME0_LUMA = (90.0, 170.0)
FRAME0_CONTRAST = (0.18, 0.45)
BLINK_DROP = 0.35
# Gate j (PLAN.md §7.4): the finished Short's integrated loudness and true peak, measured on the encoded file.
LUFS = (-15.0, -13.0)
TRUE_PEAK = -1.0
# The bed under the voice, at the level it reaches in the finished mix: at most this (PLAN.md §7.4 j).
MUSIC_BED = -20.0
ENDING_LINES = {"register-line": "झब्बू के रजिस्टर में एक और रात दर्ज", "open-question": "आपका जवाब नीचे लिखिए",
                "next-raat-tease": "पूरी रात · शनिवार शाम 7:30"}


class ComposeHold(RuntimeError):
    """The rendered Short fails a picture check: hold it."""
BELL_LEAD = 0.35  # the bell rings this long before the twist line
MOTIONS = [
    {"z": (1.00, 1.09), "dz": (0.00, 0.07), "pan": (0, 0, 0, -20), "par": (0, 0)},  # push in
    {"z": (1.05, 1.07), "dz": (0.02, 0.03), "pan": (-45, 45, 0, 0), "par": (34, 0)},  # drift right
    {"z": (1.10, 1.02), "dz": (0.07, 0.01), "pan": (0, 0, 10, -10), "par": (0, 0)},  # pull back
    {"z": (1.05, 1.08), "dz": (0.02, 0.04), "pan": (40, -40, 0, 0), "par": (-34, 0)},  # drift left
    {"z": (1.04, 1.08), "dz": (0.02, 0.05), "pan": (0, 0, 40, -40), "par": (0, 26)},  # rise
]


@functools.lru_cache(maxsize=None)
def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    if not features.check("raqm"):
        raise RuntimeError("Pillow has no RAQM text layout here; Devanagari would be drawn wrongly")
    return ImageFont.truetype(str(FONTS / WEIGHTS[weight]), size, layout_engine=ImageFont.Layout.RAQM)


@functools.lru_cache(maxsize=None)
def _glyphs(weight: str = "Medium") -> frozenset[int]:
    from fontTools.ttLib import TTFont

    return frozenset(TTFont(str(FONTS / WEIGHTS[weight])).getBestCmap())


def drawable(text: str, weight: str = "Medium") -> str:
    """text without the characters Mukta has no glyph for (a title's emoji)."""
    have = _glyphs(weight)
    kept = "".join(ch for ch in text if ord(ch) in have or ch in "\u200c\u200d")
    return re.sub(r"\s{2,}", " ", kept).strip()


def _ease(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


class Plate:
    """One painting prepared for camera moves: RGB and depth at plate size, filling the frame."""

    def __init__(self, path: Path | None = None, *, img: Image.Image | None = None, dep: np.ndarray | None = None):
        """From a painting on disk, or from a picture and its depth already in hand (a crop of a still)."""
        if img is None:
            img = Image.open(path).convert("RGB")
            dep = depth.estimate(img, path.with_suffix(".depth.npy"))
        pw, ph = round(W * MARGIN), round(H * MARGIN)
        iw, ih = img.size
        scale = max(pw / iw, ph / ih)
        sw, sh = round(iw * scale), round(ih * scale)
        x0, y0 = (sw - pw) // 2, (sh - ph) // 2
        rgb = img.resize((sw, sh), Image.LANCZOS).crop((x0, y0, x0 + pw, y0 + ph))
        d = cv2.resize(dep, (sw, sh), interpolation=cv2.INTER_LINEAR)[y0:y0 + ph, x0:x0 + pw]
        arr = np.asarray(rgb, dtype=np.float32)
        target, low, high = EXPOSURE
        gain = min(max(target / max(float(arr.mean()), 1.0), low), high)
        self.rgb = np.clip(arr * gain, 0, 255).astype(np.uint8)
        self.depth = cv2.GaussianBlur(d.astype(np.float32), (0, 0), 3) - 0.5
        self.pw, self.ph = pw, ph


class Camera:
    def __init__(self):
        gx, gy = np.meshgrid(np.arange(W, dtype=np.float32) - W / 2, np.arange(H, dtype=np.float32) - H / 2)
        self.gx, self.gy = gx, gy

    def shoot(self, plate: Plate, u: float, motion: dict, punch: float = 0.0) -> np.ndarray:
        e = _ease(u)
        z = (motion["z"][0] + (motion["z"][1] - motion["z"][0]) * e) * (1 + punch)
        dz = motion["dz"][0] + (motion["dz"][1] - motion["dz"][0]) * e
        px0, px1, py0, py1 = motion["pan"]
        cx = plate.pw / 2 + px0 + (px1 - px0) * e
        cy = plate.ph / 2 + py0 + (py1 - py0) * e
        parx, pary = motion["par"][0] * (e - 0.5), motion["par"][1] * (e - 0.5)
        # OpenCV 5 remaps only float32 maps, and a NumPy scalar (a float64 u, an int64 plate size) promotes to float64.
        f32 = np.float32
        bx = (cx + self.gx / z).astype(f32, copy=False)
        by = (cy + self.gy / z).astype(f32, copy=False)
        d = cv2.remap(plate.depth, bx, by, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        zz = 1 + dz * d * 2
        mx = (cx + self.gx / (z * zz) - parx * d * 2).astype(f32, copy=False)
        my = (cy + self.gy / (z * zz) - pary * d * 2).astype(f32, copy=False)
        return cv2.remap(plate.rgb, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


class Grade:
    """Teal shadows, amber highlights, a soft vignette (never below VIGNETTE_FLOOR), a darker band behind the
    captions, a shadow lift and film grain."""

    def __init__(self, seed: int):
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.45) / (H * 0.7)) ** 2)
        vignette = np.clip(1.08 - 0.6 * r ** 2.2, VIGNETTE_FLOOR, 1.0)
        band = 1 - 0.22 * np.exp(-((yy - H * CAPTION_Y) / (H * 0.09)) ** 2)
        self.mask = (vignette * band)[..., None].astype(np.float32)
        self.teal = np.array([0.88, 1.0, 1.08], np.float32)
        self.amber = np.array([1.1, 1.0, 0.86], np.float32)
        rng = np.random.default_rng(seed)
        self.grain = [rng.normal(0, 5.0, (H // 2, W // 2, 1)).astype(np.float32) for _ in range(4)]

    def apply(self, frame: np.ndarray, i: int) -> np.ndarray:
        f = frame.astype(np.float32)
        gray = f.mean(axis=2, keepdims=True)
        f = gray + (f - gray) * 0.9
        lum = np.clip(gray / 255.0, 0, 1)
        f = (f - 128) * 1.08 + 128
        f = f * (self.teal + (self.amber - self.teal) * lum) * self.mask
        f = LIFT + f * (1 - LIFT / 255.0)
        g = cv2.resize(self.grain[i % 4], (W, H), interpolation=cv2.INTER_NEAREST)[..., None]
        return np.clip(f + g, 0, 255).astype(np.uint8)


def _rgba(img: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(img, dtype=np.float32)
    return a[..., :3], a[..., 3:4] / 255.0


def _blit(frame: np.ndarray, layer: tuple[np.ndarray, np.ndarray], x: int, y: int, alpha: float = 1.0) -> None:
    rgb, a = layer
    h, w = a.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    sub = frame[y0:y1, x0:x1].astype(np.float32)
    la = a[y0 - y:y1 - y, x0 - x:x1 - x] * alpha
    frame[y0:y1, x0:x1] = (sub * (1 - la) + rgb[y0 - y:y1 - y, x0 - x:x1 - x] * la).astype(np.uint8)


def _text_layer(lines: list[tuple[str, ImageFont.FreeTypeFont, tuple]], stroke: int = 0, gap: int = 8,
                pad: int = 0, box: tuple | None = None) -> Image.Image:
    sizes = [f.getbbox(t, stroke_width=stroke) for t, f, _ in lines]
    w = max(b[2] - b[0] for b in sizes) + 2 * pad
    h = sum(b[3] - b[1] for b in sizes) + gap * (len(lines) - 1) + 2 * pad
    img = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if box:
        d.rounded_rectangle((0, 0, w, h), radius=18, fill=box)
    y = pad
    for (t, f, color), b in zip(lines, sizes):
        x = pad + (0 if box else (w - 2 * pad - (b[2] - b[0])) // 2)
        d.text((x - b[0], y - b[1]), t, font=f, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
        y += b[3] - b[1] + gap
    return img


CAPTION_SIZE, CAPTION_STROKE = 92, 9
CAPTION_WIDTH = TEXT_W - 40
BREAKS = ".,;:!?—।॥…"


def _chunks(words: list[dict], width=None) -> list[list[dict]]:
    """Caption groups of up to three words that fit on one line, ending at punctuation (। included)."""
    width = width or (lambda text: len(text) * CAPTION_SIZE * 0.42)
    out, cur = [], []
    for w in words:
        if cur and width(" ".join(x["text"] for x in cur + [w])) > CAPTION_WIDTH:
            out.append(cur)
            cur = []
        cur.append(w)
        if len(cur) >= 3 or w["text"][-1:] in BREAKS:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


class Captions:
    def __init__(self, words: list[dict], accent: tuple):
        self.font = _font("ExtraBold", CAPTION_SIZE)
        self.accent = accent
        self.groups = []
        for chunk in _chunks(words, lambda text: self.font.getlength(text) + 2 * CAPTION_STROKE):
            texts = [w["text"] for w in chunk]
            variants = [self._render(texts, k) for k in range(len(chunk))]
            self.groups.append({"start": chunk[0]["start"], "end": chunk[-1]["end"], "words": chunk,
                                "variants": variants})

    def _render(self, texts: list[str], active: int) -> tuple[np.ndarray, np.ndarray]:
        stroke = CAPTION_STROKE
        space = self.font.getlength(" ")
        widths = [self.font.getlength(t) + 2 * stroke for t in texts]
        ascent, descent = self.font.getmetrics()
        total = int(sum(widths) + space * (len(texts) - 1)) + 24
        img = Image.new("RGBA", (total, ascent + descent + 2 * stroke + 16), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x = 12
        for i, (t, w) in enumerate(zip(texts, widths)):
            color = self.accent + (255,) if i == active else (255, 255, 255, 255)
            d.text((x + stroke, 8 + stroke), t, font=self.font, fill=color, stroke_width=stroke,
                   stroke_fill=(0, 0, 0, 255))
            x += w + space
        if img.width > TEXT_W:
            img = img.resize((TEXT_W, round(img.height * TEXT_W / img.width)), Image.LANCZOS)
        return _rgba(img)

    def draw(self, frame: np.ndarray, t: float) -> None:
        for g in self.groups:
            if g["start"] - 0.05 <= t < g["end"] + 0.12:
                k = max([i for i, w in enumerate(g["words"]) if w["start"] <= t + 0.03] or [0])
                layer = g["variants"][k]
                h, w = layer[1].shape[:2]
                pop = min(1.0, (t - g["start"] + 0.05) / 0.09)
                if pop < 1:
                    s = 0.9 + 0.1 * pop
                    rgb = cv2.resize(layer[0], (max(1, round(w * s)), max(1, round(h * s))))
                    a = cv2.resize(layer[1], (max(1, round(w * s)), max(1, round(h * s))))[..., None]
                    layer, (h, w) = (rgb, a), a.shape[:2]
                _blit(frame, layer, TEXT_CX - w // 2, round(H * CAPTION_Y - h / 2))
                return


def _fit(weight: str, size: int, text: str, width: int, floor: int = 24) -> ImageFont.FreeTypeFont:
    font = _font(weight, size)
    while font.getlength(text) > width and font.size > floor:
        font = _font(weight, font.size - 3)
    return font


def _label_layer(text: str = AI_LABEL) -> tuple[np.ndarray, np.ndarray]:
    """The AI and fiction label: small, in the top-left corner, on every frame."""
    return _rgba(_text_layer([(text, _font("SemiBold", 28), (255, 255, 255, 235))], pad=10, box=(10, 12, 16, 170)))


LABEL_AT = (SIDE - 12, 26)


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        if cur and font.getlength(f"{cur} {w}") > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + [cur] if cur else lines


def _strip_layer(strip: str) -> tuple[np.ndarray, np.ndarray]:
    """The hook strip over frame 0: 3-5 words, large, on a dark band whose height is STRIP_SHARE of the frame and
    which ends inside the top third."""
    text = drawable(hindi.EMOJI.sub("", strip).replace("\ufe0f", ""), "ExtraBold")
    room = min(STRIP_SHARE[1], 1 / 3 - STRIP_TOP) * H
    for size in range(124, 50, -6):
        font = _font("ExtraBold", size)
        lines = _wrap(text, font, TEXT_W - 56)
        if len(lines) <= 2 and all(font.getlength(ln) <= TEXT_W - 56 for ln in lines):
            img = _text_layer([(ln, font, ACCENT + (255,) if i == 0 else (255, 255, 255, 255))
                               for i, ln in enumerate(lines)], stroke=6, gap=18, pad=28)
            if img.height <= room:
                break
    rgb, a = _rgba(img)
    h = a.shape[0]
    want = max(h, round(STRIP_SHARE[0] * H) + 2)
    band = np.zeros((want, TEXT_W, 4), np.float32)
    band[..., 3] = 0.62
    y0, x0 = (want - h) // 2, max((TEXT_W - a.shape[1]) // 2, 0)
    w = min(a.shape[1], TEXT_W)
    under = band[y0:y0 + h, x0:x0 + w]
    la = a[:, :w]
    under[..., :3] = rgb[:, :w] * la + under[..., :3] * (1 - la)
    under[..., 3:4] = la + under[..., 3:4] * (1 - la)
    return band[..., :3], band[..., 3:4]


def _headline_layer(title: str) -> tuple[np.ndarray, np.ndarray]:
    """The title without its emoji as a hook strip (stories made before F1 have no hook_strip)."""
    return _strip_layer(title)


def _end_layers(ending: str = "") -> list[tuple[np.ndarray, np.ndarray]]:
    """The end card: the channel's name, what it tells, the ending's line, and the fiction and AI disclosure. No
    like or subscribe asks."""
    layers = [_rgba(_text_layer([(config.NAME, _fit("ExtraBold", 112, config.NAME, TEXT_W), ACCENT + (255,))])),
              _rgba(_text_layer([(config.TAGLINE, _fit("SemiBold", 48, config.TAGLINE, TEXT_W), (255, 255, 255, 240))]))]
    if ending in ENDING_LINES:
        line = ENDING_LINES[ending]
        layers.append(_rgba(_text_layer([(line, _fit("Bold", 58, line, TEXT_W), (255, 255, 255, 250))])))
    layers.append(_rgba(_text_layer([(END_LINE, _fit("Medium", 34, END_LINE, TEXT_W), (255, 255, 255, 215))])))
    return layers


END_AT = (0.30, 0.39, 0.47, 0.55)


def ink(draw) -> np.ndarray:
    """Where draw(canvas) puts anything on a frame (bool H x W): the overlays drawn on a black and a white canvas, so
    a black stroke and a white letter both count."""
    dark, light = np.zeros((H, W, 3), np.uint8), np.full((H, W, 3), 255, np.uint8)
    draw(dark)
    draw(light)
    return (dark != 0).any(axis=2) | (light != 255).any(axis=2)


def _runs(rows: np.ndarray) -> list[tuple[int, int]]:
    edges = np.flatnonzero(np.diff(np.concatenate([[0], rows.astype(np.int8), [0]])))
    return list(zip(edges[::2], edges[1::2]))


def text_problems(first: np.ndarray, others: list[np.ndarray], label_right: int) -> list[str]:
    """Gate g on the drawn frames: frame 0's hook strip inside STRIP_SHARE of the height and the top third; no ink
    below SAFE_BOTTOM or right of SAFE_RIGHT on any checked frame. first/others are ink() masks; the strip is measured
    right of the AI label (label_right) so the label never counts as strip."""
    found = []
    runs = _runs(first[:, label_right + 8:round(W * SAFE_RIGHT)].any(axis=1))
    if not runs:
        found.append("frame 0 has no hook strip")
    else:
        top, bottom = runs[0]
        share = (bottom - top) / H
        if not STRIP_SHARE[0] <= share <= STRIP_SHARE[1]:
            found.append(f"frame 0's hook strip is {share:.0%} of the height, needs {STRIP_SHARE[0]:.0%}-"
                         f"{STRIP_SHARE[1]:.0%}")
        if bottom > H / 3:
            found.append("frame 0's hook strip runs below the top third")
    for n, mask in enumerate([first] + others):
        where = "frame 0" if n == 0 else f"checked frame {n}"
        if mask[round(H * SAFE_BOTTOM):].any():
            found.append(f"{where} has text below {SAFE_BOTTOM:.0%} of the height")
        if mask[:, round(W * SAFE_RIGHT):].any():
            found.append(f"{where} has text in the right {1 - SAFE_RIGHT:.0%} (the Shorts buttons)")
    return found


def problems(lumas: list[float], cuts: set[int], frame0: np.ndarray, expected: int, counted: int | None) -> list[str]:
    """The picture checks (PLAN.md §7.4 gates g and k): frame 0's exposure and contrast, blinks, frame count (a count
    that could not be made holds too)."""
    found = []
    gray = cv2.cvtColor(frame0, cv2.COLOR_RGB2GRAY).astype(np.float32)
    luma, contrast = float(gray.mean()), float(gray.std() / 255.0)
    if not FRAME0_LUMA[0] <= luma <= FRAME0_LUMA[1]:
        found.append(f"frame 0 mean luma {luma:.0f}, needs {FRAME0_LUMA[0]:.0f}-{FRAME0_LUMA[1]:.0f}")
    if not FRAME0_CONTRAST[0] <= contrast <= FRAME0_CONTRAST[1]:
        found.append(f"frame 0 RMS contrast {contrast:.2f}, needs {FRAME0_CONTRAST[0]}-{FRAME0_CONTRAST[1]}")
    for i in range(1, len(lumas)):
        if i not in cuts and lumas[i - 1] > 1 and (lumas[i - 1] - lumas[i]) / lumas[i - 1] > BLINK_DROP:
            found.append(f"frame {i} blinks: luma drops {lumas[i - 1]:.0f} -> {lumas[i]:.0f} outside a cut")
            break
    if counted is None:
        found.append("the encoded Short's frames could not be counted")
    elif abs(counted - expected) > 1:
        found.append(f"the encoded Short has {counted} frames, expected {expected}")
    return found


def loudness(path: Path) -> dict | None:
    """{"lufs", "true_peak"} of a file's audio (ffmpeg ebur128 summary), or None when it cannot be measured."""
    try:
        err = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-filter_complex",
                              "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True,
                             check=True).stderr
    except (OSError, subprocess.CalledProcessError):
        return None
    summary = err[err.rfind("Summary:"):]
    lufs = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summary)
    peak = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if not lufs or not peak:
        return None
    return {"lufs": float(lufs.group(1)), "true_peak": float(peak.group(1))}


def audio_problems(m: dict | None, bed: float | None = None) -> list[str]:
    """Gate j: integrated loudness inside LUFS (floor and ceiling), true peak at most TRUE_PEAK, and the music bed under
    the voice (bed, LUFS in the finished mix; see bed_level) at most MUSIC_BED. A level that could not be measured
    holds."""
    if not m:
        return ["the Short's loudness could not be measured"]
    found = []
    if not LUFS[0] <= m["lufs"] <= LUFS[1]:
        found.append(f"integrated loudness {m['lufs']:.1f} LUFS, needs {LUFS[0]:.0f} to {LUFS[1]:.0f}")
    if m["true_peak"] > TRUE_PEAK:
        found.append(f"true peak {m['true_peak']:.1f} dBTP, needs at most {TRUE_PEAK}")
    if bed is None:
        found.append("the music bed's level could not be measured")
    elif bed > MUSIC_BED:
        found.append(f"the music bed is {bed:.1f} LUFS under the voice, needs at most {MUSIC_BED:.0f}")
    return found


def bed_level(levels: dict | None, final: dict | None) -> float | None:
    """The ducked bed's loudness as it lands in the finished Short: measured before the mix's loudnorm, moved by the
    gain loudnorm gave the whole mix (final minus the mix before it). None when any of them is missing."""
    if not levels or not final or levels.get("bed") is None or levels.get("premix") is None:
        return None
    if levels["bed"] == float("-inf"):
        return levels["bed"]
    return levels["bed"] + final["lufs"] - levels["premix"]


def count_frames(path: Path) -> int | None:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                              "stream=nb_read_frames", "-of", "csv=p=0", str(path)], capture_output=True, text=True,
                             check=True).stdout.strip()
        return int(out.split(",")[0])
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def length(path: Path) -> float | None:
    """The encoded file's duration in seconds (ffprobe), or None."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(path)], capture_output=True, text=True, check=True).stdout.strip()
        return float(out)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None


def bell_time(story: Story, spans: list) -> float | None:
    twist = story.twist_beat - 1
    return max(spans[twist][0] - BELL_LEAD, 0.0) if 0 <= twist < len(spans) else None


def _mix(narration: Path, story: Story, seconds: float, bell_at: float | None, out: Path) -> tuple[Path, dict]:
    """mix.wav, and the levels gate j's bed ceiling needs: the ducked bed while the voice speaks (bed.wav) and the mix
    before its loudnorm (premix.wav), both in LUFS."""
    import soundfile as sf

    bed = music.score(seconds + 0.5, story.id, bell_at)
    sf.write(out / "music.wav", bed, music.SR)
    spoken = sf.info(str(narration)).duration
    mixed = out / "mix.wav"
    graph = ("[0:a]aresample=48000,highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,"
             "volume=1.0,asplit=2[v][key];"
             "[1:a]aresample=48000,volume=0.32[m];"
             "[m][key]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=500,asplit=2[duck][b];"
             f"[b]atrim=0:{spoken:.3f}[bed];"
             "[v][duck]amix=inputs=2:duration=first:normalize=0,asplit=2[mx][pre];"
             f"[mx]loudnorm=I=-14:TP=-1.5:LRA=9,apad,atrim=0:{seconds:.3f}[out]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(narration), "-i", str(out / "music.wav"),
                    "-filter_complex", graph, "-map", "[out]", "-ar", "48000", "-ac", "2", str(mixed),
                    "-map", "[bed]", "-ar", "48000", str(out / "bed.wav"),
                    "-map", "[pre]", "-ar", "48000", str(out / "premix.wav")], check=True)
    levels = {k: (loudness(out / f"{k}.wav") or {}).get("lufs") for k in ("bed", "premix")}
    return mixed, levels


def render(story: Story, timing: dict, pictures: list[Path], work: Path) -> dict:
    """short.mp4 (1080x1920, 30 fps, H.264 + AAC) and a few stills. pictures holds one path per beat."""
    plates = {p: Plate(p) for p in dict.fromkeys(pictures)}
    cam, grade = Camera(), Grade(seed=len(story.id))
    captions = Captions(timing["words"], ACCENT)
    spoken = timing["duration"]
    duration = spoken + END_CARD
    spans = timing["beats"]
    shots = [{"plate": plates[pictures[i]], "start": s if i else 0.0, "end": e if i < len(spans) - 1 else duration,
              "motion": MOTIONS[i % len(MOTIONS)]} for i, (s, e) in enumerate(spans)]
    strip = _strip_layer(story.hook_strip) if story.hook_strip else _headline_layer(story.title)
    label, end = _label_layer(), _end_layers(story.ending)
    loop = story.ending == "loop-back"
    lumas: list[float] = []
    cuts: set[int] = set()
    frame0 = None
    work.mkdir(parents=True, exist_ok=True)
    mixed, levels = _mix(work / "narration.wav", story, duration, bell_time(story, spans), work)
    out = work / "short.mp4"
    stills = work / "stills"
    stills.mkdir(exist_ok=True)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", str(mixed), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    n = int(math.ceil(duration * FPS))
    still_at = {int(n * k / 5) for k in range(5)}
    # Frame 0, the stills, a caption mid-story and the last frame (the end card) are checked for where text lands.
    inked, masks = sorted(still_at | {n // 2, n - 1}), []
    for i in range(n):
        t = i / FPS
        k = next(j for j, s in enumerate(shots) if t < s["end"] or j == len(shots) - 1)
        shot = shots[k]
        u = (t - shot["start"]) / max(shot["end"] - shot["start"], 0.1)
        punch = 0.035 * max(0.0, 1 - (t - shot["start"]) / 0.35) if k else 0.06 * max(0.0, 1 - t / 0.6)
        frame = cam.shoot(shot["plate"], u, shot["motion"], punch)
        if k and (t - shot["start"]) * FPS < CROSSFADE:
            prev = shots[k - 1]
            pu = (t - prev["start"]) / max(prev["end"] - prev["start"], 0.1)
            a = (t - shot["start"]) * FPS / CROSSFADE
            frame = cv2.addWeighted(frame, a, cam.shoot(prev["plate"], pu, prev["motion"]), 1 - a, 0)
        if k and (t - shot["start"]) * FPS < CROSSFADE + 1:
            cuts.add(i)
        outro = t >= spoken
        if outro and loop:
            # A loop-back ends on frame 0 again (the hook's painting and strip), so the replay is seamless.
            fade = min(1.0, (t - spoken) / 0.6)
            frame = cv2.addWeighted(cam.shoot(shots[0]["plate"], 0.0, shots[0]["motion"]), fade, frame, 1 - fade, 0)
        elif outro:
            fade = min(1.0, (t - spoken) / 0.5)
            frame = cv2.addWeighted(cv2.GaussianBlur(frame, (0, 0), 18), 0.55 * fade, frame, 1 - 0.8 * fade, 0)
        if outro and (t - spoken) * FPS < 0.6 * FPS + 1:
            cuts.add(i)
        frame = grade.apply(frame, i)

        def overlays(canvas: np.ndarray, t=t, k=k, outro=outro) -> None:
            if k == 0 or (outro and loop):
                # Fully visible from the first frame: YouTube may use it as the cover.
                a = 1.0 if k == 0 and not outro else min(1.0, (t - spoken) / 0.6)
                _blit(canvas, strip, TEXT_CX - strip[1].shape[1] // 2, round(H * STRIP_TOP), a)
            if outro and not loop:
                a = min(1.0, (t - spoken) / 0.4)
                for layer, y in zip(end, END_AT[:len(end) - 1] + (END_AT[-1],)):
                    _blit(canvas, layer, TEXT_CX - layer[1].shape[1] // 2, round(H * y), a)
            elif not outro:
                captions.draw(canvas, t)
            _blit(canvas, label, *LABEL_AT)

        overlays(frame)
        if i in inked:
            masks.append(ink(overlays))
        if i == 0:
            frame0 = frame.copy()
        lumas.append(float(frame[::8, ::8].mean()))
        enc.stdin.write(frame.tobytes())
        if i in still_at:
            Image.fromarray(frame).save(stills / f"t{i // FPS:03d}.png")
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the Short")
    sound = loudness(out)
    bed = bed_level(levels, sound)
    found = problems(lumas, cuts, frame0, n, count_frames(out)) + audio_problems(sound, bed) + \
        text_problems(masks[0], masks[1:], LABEL_AT[0] + label[1].shape[1])
    (work / "picture-checks.json").write_text(json.dumps({"problems": found, "frames": n, "loudness": sound,
                                                          "bed_lufs": bed, "levels": levels},
                                                         indent=1, ensure_ascii=False), encoding="utf-8")
    if found:
        raise ComposeHold("hold: picture and sound checks: " + "; ".join(found))
    return {"duration": round(duration, 2), "frames": n, "pictures": len(plates), "fps": FPS, "size": [W, H],
            "runtime": length(out)}


# ---- Format M: the wordless moment ------------------------------------------------------------------------------------
# 16 hard cuts between crops of 4-6 paintings (an anomaly card drawn onto a wall by card.py), no captions and no voice,
# a hook strip and a typed time stamp at the start, an end card, the last episode's answer, and a soft return to frame 0.
MOMENT_LABEL = "AI चित्र · काल्पनिक"
MOMENT_END_LINE = "यह दृश्य काल्पनिक है · चित्र: AI · ध्वनि: कोड से"
HOOK_UNTIL = 3.0  # seconds the hook strip stays on
STAMP = (0.3, 0.9, 3.0)  # the time stamp starts typing here, takes this long, and is gone by the last
STAMP_AT = 0.60  # share of the height
FLICKER_AMP, FLICKER_HZ = 0.04, 2.4  # a lamp's pulse: 8% peak to peak, under the 3 Hz line
LOOP_FADE = 0.88  # how far the last frames get to frame 0 (a seamless loop feels like a cheat; a soft one doesn't)
CUT_STEP, CUT_DIFF, CUT_MERGE = 4, 10.0, 0.4  # a picture change: thumbnails 4 frames apart differ by more than this
QUIET_LUFS, MOTIF_MAX = -45.0, -18.0
THUMB = (54, 96)


def picture_changes(thumbs: list[np.ndarray]) -> list[float]:
    """Seconds at which the picture changes (a cut): the first frame of each run where thumbnails CUT_STEP frames apart
    differ by more than CUT_DIFF (mean over 0-255), runs closer than CUT_MERGE merged."""
    found: list[float] = []
    over = False
    for i in range(CUT_STEP, len(thumbs)):
        hit = float(np.abs(thumbs[i].astype(np.int16) - thumbs[i - CUT_STEP].astype(np.int16)).mean()) > CUT_DIFF
        at = (i - CUT_STEP + 1) / FPS
        if hit and not over and (not found or at - found[-1] > CUT_MERGE):
            found.append(at)
        over = hit
    return found


def quiet_stretch(path: Path, floor: float = QUIET_LUFS) -> float | None:
    """The longest run of seconds the momentary loudness (ebur128 M) stays below floor, or None when unmeasurable."""
    try:
        err = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-v", "verbose", "-i", str(path), "-filter_complex",
                              "ebur128=framelog=verbose", "-f", "null", "-"], capture_output=True, text=True,
                             check=True).stderr
    except (OSError, subprocess.CalledProcessError):
        return None
    rows = re.findall(r"t:\s*([\d.]+)\s+TARGET:\S+ LUFS\s+M:\s*(-?[\d.]+|-?inf|nan)", err)
    if not rows:
        return None
    best, start = 0.0, None
    for t, m in rows:
        t = float(t)
        if m in ("nan", "-inf", "inf") or float(m) < floor:
            start = t if start is None else start
            best = max(best, t - start + 0.1)
        else:
            start = None
    return round(best, 2)


def _moment_mix(story: Story, seconds: float, work: Path) -> tuple[Path, dict]:
    """mix.wav: the foley and the motif summed, limited, and
    moved by whole-mix gain until it measures -14 LUFS with its true peak at most TRUE_PEAK. Returns the path and the
    measurements the gate wants (loudness, the longest quiet stretch, the motif's own loudness)."""
    import soundfile as sf

    from . import moment

    bed, mo = music.foley(moment.sfx_cues(story), seconds + 0.5, story.id)
    raw = bed + mo
    mixed, probe = work / "mix.wav", work / "probe.wav"
    sf.write(probe, raw, music.SR, subtype="FLOAT")
    db, sound = 8.0, None
    for _ in range(6):
        chain = f"aresample=48000,volume={db:.2f}dB,alimiter=limit=0.84:attack=3:release=80:level=disabled"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(probe), "-af", chain, "-ar", "48000", "-ac",
                        "2", str(mixed)], check=True)
        sound = loudness(mixed)
        if not sound or (abs(sound["lufs"] + 14.0) <= 0.4 and sound["true_peak"] <= TRUE_PEAK):
            break
        db += -14.0 - sound["lufs"]
    # the motif alone, through the same gain and no limiter: what it adds to the mix
    sf.write(probe, mo * 10 ** (db / 20), music.SR, subtype="FLOAT")
    motif = loudness(probe)
    return mixed, {"loudness": sound, "quiet_stretch": quiet_stretch(mixed),
                   "motif_lufs": motif["lufs"] if motif else None}


class _Plates:
    """A moment's camera plates: each shot is a crop of one of the stills with the anomaly card drawn onto its wall.
    Built when first needed (a ticking clock needs a new one each second) and dropped once the cut has passed."""

    def __init__(self, story: Story, pictures: list[Path]):
        from . import card, moment

        self.story, self.card = story, card
        self.anomaly = moment.card_of(story)
        self.seed = len(story.id)
        self.base: list[tuple[np.ndarray, np.ndarray]] = []
        for p in pictures:
            img = Image.open(p).convert("RGB")
            dep = depth.estimate(img, Path(p).with_suffix(".depth.npy"))
            self.base.append((np.asarray(img.resize((img.width * 2, img.height * 2), Image.LANCZOS)), dep))
        self.cache: dict[tuple[int, int], Plate] = {}

    def at(self, k: int, t: float) -> Plate:
        shot = self.story.shots[k]
        places = [p for p in (self.anomaly or {}).get("placements", []) if p["still"] == shot["still"]]
        state = self.card.state(self.anomaly["kind"], t) if places else 0
        if (k, state) not in self.cache:
            rgb, dep = self.base[shot["still"]]
            for p in places:
                art, _ = self.card.render(self.anomaly["kind"], self.anomaly["spec"], float(state))
                rgb = self.card.composite(rgb, art, p["quad"], seed=self.seed + k)
            x0, y0, w = shot["box"]
            (rh, rw), (dh, dw) = rgb.shape[:2], dep.shape[:2]
            c = rgb[round(y0 * rh):round((y0 + w) * rh), round(x0 * rw):round((x0 + w) * rw)]
            d = dep[round(y0 * dh):round((y0 + w) * dh), round(x0 * dw):round((x0 + w) * dw)]
            self.cache = {key: v for key, v in self.cache.items() if key[0] >= k - 1}
            self.cache[(k, state)] = Plate(img=Image.fromarray(np.ascontiguousarray(c)), dep=np.ascontiguousarray(d))
        return self.cache[(k, state)]


def render_moment(story: Story, timing: dict, pictures: list[Path], work: Path) -> dict:
    """short.mp4 for a moment, and the numbers gate.check_moment reads (picture changes, flicker, loudness, loop)."""
    from . import card as cardmod, moment

    duration, spans, end, tail, loop = (timing["duration"], timing["beats"], timing["end"], timing["tail"],
                                        timing["loop"])
    plates, cam, grade = _Plates(story, pictures), Camera(), Grade(seed=len(story.id))
    strip, label = _strip_layer(story.hook_strip), _label_layer(MOMENT_LABEL)
    stamp = _rgba(_text_layer([(story.stamp, _font("ExtraBold", 84), ACCENT + (255,))], stroke=6))
    ask_font = _font("Bold", 58)
    asks = _wrap(story.cta_text, ask_font, TEXT_W - 40)
    name = _rgba(_text_layer([(config.NAME, _fit("ExtraBold", 112, config.NAME, TEXT_W), ACCENT + (255,))]))
    disclosure = _fit("Medium", 34, MOMENT_END_LINE, TEXT_W)
    end_layers = [(name, 0.20), (_rgba(_text_layer([(ln, ask_font, (255, 255, 255, 250)) for ln in asks], gap=14)), 0.34),
                  (_rgba(_text_layer([(MOMENT_END_LINE, disclosure, (255, 255, 255, 215))])), 0.60)]
    answer, answer_info = None, None
    if tail:
        prev = moment.card_of(story, "previous")
        answer, answer_info = cardmod.answer_card(prev, prev["text"], prev["register"])
    work.mkdir(parents=True, exist_ok=True)
    mixed, audio = _moment_mix(story, duration, work)
    out, stills = work / "short.mp4", work / "stills"
    stills.mkdir(exist_ok=True)
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-i", str(mixed), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE)
    n = int(math.ceil(duration * FPS))
    last = len(spans) - 1
    motion = lambda k: MOTIONS[story.shots[k]["motion"] % len(MOTIONS)]  # noqa: E731
    starts = [s for s, _ in spans] + [end[0]] + ([tail[0]] if tail else [])
    cuts = {c for t0 in starts for c in range(round(t0 * FPS), round(t0 * FPS) + 3)}
    cuts |= set(range(round(end[0] * FPS), round((end[0] + 0.4) * FPS) + 2)) | set(range(round(loop[0] * FPS), n))
    still_at = {int(n * k / 5) for k in range(5)}
    inked, masks = sorted(still_at | {n // 2, n - 1}), []
    lumas, thumbs, frame0, final = [], [], None, None
    for i in range(n):
        t = i / FPS
        if t < end[0]:
            k = next(j for j, (a, b) in enumerate(spans) if t < b or j == last)
            a, b = spans[k]
            frame = cam.shoot(plates.at(k, t), (t - a) / (b - a), motion(k), 0.03 * max(0.0, 1 - (t - a) / 0.25))
            frame = cv2.convertScaleAbs(frame, alpha=1 + FLICKER_AMP * math.sin(2 * math.pi * FLICKER_HZ * t))
            phase = "shot"
        elif tail and t >= tail[0]:
            frame, phase = answer, "tail"
        else:
            fade = min(1.0, (t - end[0]) / 0.4)
            frame = cam.shoot(plates.at(last, spans[last][1]), 1.0, motion(last))
            frame = cv2.addWeighted(cv2.GaussianBlur(frame, (0, 0), 18), 0.55 * fade, frame, 1 - 0.8 * fade, 0)
            phase = "end"
        if t >= loop[0]:
            mix = LOOP_FADE * min(1.0, (t - loop[0]) / (loop[1] - loop[0]))
            frame = cv2.addWeighted(cam.shoot(plates.at(0, 0.0), 0.0, motion(0)), mix, frame, 1 - mix, 0)
            phase = "loop"
        thumbs.append(cv2.resize(frame, THUMB, interpolation=cv2.INTER_AREA))
        frame = grade.apply(frame, i)

        def overlays(canvas: np.ndarray, t=t, phase=phase) -> None:
            if phase == "shot" and t < HOOK_UNTIL:
                _blit(canvas, strip, TEXT_CX - strip[1].shape[1] // 2, round(H * STRIP_TOP),
                      min(1.0, (HOOK_UNTIL - t) / 0.3))
            elif phase == "loop":
                _blit(canvas, strip, TEXT_CX - strip[1].shape[1] // 2, round(H * STRIP_TOP),
                      min(1.0, (t - loop[0]) / (loop[1] - loop[0])))
            if phase == "shot" and STAMP[0] <= t < STAMP[2]:
                cols = max(1, round(stamp[1].shape[1] * min(1.0, (t - STAMP[0]) / STAMP[1])))
                _blit(canvas, (stamp[0][:, :cols], stamp[1][:, :cols]), TEXT_CX - stamp[1].shape[1] // 2,
                      round(H * STAMP_AT), min(1.0, (STAMP[2] - t) / 0.3))
            if phase == "end":
                for layer, y in end_layers:
                    _blit(canvas, layer, TEXT_CX - layer[1].shape[1] // 2, round(H * y), min(1.0, (t - end[0]) / 0.4))
            _blit(canvas, label, *LABEL_AT)

        overlays(frame)
        if i in inked:
            masks.append(ink(overlays))
        if i == 0:
            frame0 = frame.copy()
        final = frame
        lumas.append(float(frame[::8, ::8].mean()))
        enc.stdin.write(frame.tobytes())
        if i in still_at:
            Image.fromarray(frame).save(stills / f"t{i // FPS:03d}.png")
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed to encode the Short")
    sound = loudness(out)  # the encoded file that gets published, not the pre-encode mix.wav
    flat = [float(x.mean()) for x in thumbs]
    steps = [abs(flat[i] - flat[i - 1]) / max(flat[i - 1], 1.0) for i in range(1, n) if i not in cuts]
    changes = picture_changes(thumbs)
    # There is no voice, so there is no bed under it to measure: the bed check is passed a level that always clears.
    found = problems(lumas, cuts, frame0, n, count_frames(out)) + audio_problems(sound, MUSIC_BED - 10) + \
        text_problems(masks[0], masks[1:], LABEL_AT[0] + label[1].shape[1])
    if audio["motif_lufs"] is None or audio["motif_lufs"] > MOTIF_MAX:
        found.append(f"the register motif is {audio['motif_lufs']} LUFS, needs at most {MOTIF_MAX:.0f}")
    if answer_info and answer_info["bottom"] > SAFE_BOTTOM:
        found.append(f"the answer card's text runs to {answer_info['bottom']:.0%} of the height")
    stats = {"duration": round(duration, 2), "frames": n, "pictures": len(pictures), "fps": FPS, "size": [W, H],
             "runtime": length(out), "changes": len(changes), "changes_per_10s": round(len(changes) / duration * 10, 2),
             "flicker_step": round(max(steps or [0.0]), 4),
             "loudness": sound, "quiet_stretch": audio["quiet_stretch"], "motif_lufs": audio["motif_lufs"],
             "tail": round(tail[1] - tail[0], 2) if tail else 0.0,
             "loop_diff": round(float(np.abs(final.astype(np.int16) - frame0.astype(np.int16)).mean()), 2)}
    (work / "picture-checks.json").write_text(json.dumps({"problems": found, **stats}, indent=1, ensure_ascii=False),
                                              encoding="utf-8")
    if found:
        raise ComposeHold("hold: picture and sound checks: " + "; ".join(found))
    return stats
