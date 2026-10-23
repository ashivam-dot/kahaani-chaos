"""The impossible detail of a Format M moment, drawn by code and never painted (a painted Devanagari word or numeral
comes out wrong; vision.py refuses painted text). A card is a Pillow picture of a timetable, a wall clock or a
calendar; composite() warps it onto a quad of a painted plate and grades it to sit in that plate. answer_card() is
the previous episode's card with a red circle on the odd part, for the tail of the next one.

Text is laid out with the same RAQM-shaped Mukta fonts as the captions (compose._font). A card is an opaque board (or a
round clock) with its own frame, so the painted plate only has to leave a plain wall for it.
"""
from __future__ import annotations

import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

from . import compose

KINDS = ("timetable", "clock", "calendar")
SIZES = {"timetable": (720, 600), "clock": (640, 640), "calendar": (640, 720)}
RED = (222, 38, 38)
INK = (28, 24, 20)
CREAM = (238, 230, 206)
CHALK = (244, 240, 226)
WOOD = (104, 70, 40)
BOARD = (30, 52, 44)


def _arrow(d: ImageDraw.ImageDraw, x: float, y: float, length: float, color: tuple, width: int = 5) -> float:
    """A right-pointing arrow (Mukta has no arrow glyph); returns the x where it ends."""
    d.line([(x, y), (x + length, y)], fill=color, width=width)
    d.polygon([(x + length + 4, y), (x + length - 14, y - 12), (x + length - 14, y + 12)], fill=color)
    return x + length + 8


def _timetable(spec: dict) -> tuple[Image.Image, dict]:
    w, h = SIZES["timetable"]
    img = Image.new("RGBA", (w, h), WOOD + (255,))
    d = ImageDraw.Draw(img)
    d.rectangle((22, 22, w - 23, h - 23), fill=BOARD)
    d.rectangle((22, 22, w - 23, h - 23), outline=(70, 46, 26), width=4)
    title = compose._font("ExtraBold", 54)
    d.text((w / 2, 74), spec["title"], font=title, fill=CHALK, anchor="mm")
    head = compose._font("SemiBold", 34)
    d.text((54, 146), spec["head"][0], font=head, fill=(236, 200, 120), anchor="lm")
    d.text((250, 146), spec["head"][1], font=head, fill=(236, 200, 120), anchor="lm")
    d.line([(44, 184), (w - 44, 184)], fill=(150, 150, 130), width=3)
    row_font, time_font = compose._font("Bold", 42), compose._font("Bold", 44)
    top, step = 212, 86
    boxes = []
    for i, (when, a, b) in enumerate(spec["rows"]):
        y = top + i * step
        d.text((54, y + 30), when, font=time_font, fill=CHALK, anchor="lm")
        d.text((250, y + 30), a, font=row_font, fill=CHALK, anchor="lm")
        x = 250 + row_font.getlength(a) + 16
        x = _arrow(d, x, y + 34, 38, CHALK)
        d.text((x + 8, y + 30), b, font=row_font, fill=CHALK, anchor="lm")
        boxes.append((34, y - 2, w - 34, y + 66))
        if i < len(spec["rows"]) - 1:
            d.line([(44, y + step - 12), (w - 44, y + step - 12)], fill=(70, 96, 84), width=2)
    return img, {"answer": boxes[spec["odd"]]}


def clock_hands(spec: dict, t: float) -> tuple[float, float, float]:
    """Hour, minute and second hand angles in degrees clockwise from the top, t seconds after the clock's own start
    time. The second hand ticks once a second, like the wall clocks of the day."""
    s = int(t)
    minutes = spec["m"] + s / 60.0
    hour = ((spec["h"] % 12) + minutes / 60.0) * 30.0
    return hour % 360, (minutes * 6.0) % 360, (s % 60) * 6.0


def _clock(spec: dict, t: float) -> tuple[Image.Image, dict]:
    w, h = SIZES["clock"]
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = w / 2
    d.ellipse((6, 6, w - 7, h - 7), fill=(58, 40, 26, 255))
    d.ellipse((34, 34, w - 35, h - 35), fill=CREAM + (255,))
    d.ellipse((34, 34, w - 35, h - 35), outline=(30, 20, 12, 255), width=5)
    for k in range(60):
        a = math.radians(k * 6)
        r0 = c - 62 if k % 5 == 0 else c - 52
        d.line([(c + r0 * math.sin(a), c - r0 * math.cos(a)), (c + (c - 44) * math.sin(a), c - (c - 44) * math.cos(a))],
               fill=INK + (255,), width=5 if k % 5 == 0 else 2)
    font = compose._font("ExtraBold", 66)
    boxes = {}
    for k in range(12):
        label = spec["top"] if k == 0 else str(k)
        a = math.radians(k * 30)
        x, y = c + (c - 118) * math.sin(a), c - (c - 118) * math.cos(a)
        d.text((x, y), label, font=font, fill=INK + (255,), anchor="mm")
        if k == 0:
            half = font.getlength(label) / 2
            boxes["answer"] = (x - half - 8, y - 44, x + half + 8, y + 44)
    hour, minute, second = clock_hands(spec, t)

    def hand(angle: float, length: float, width: int, color: tuple) -> None:
        a = math.radians(angle)
        d.line([(c - 0.14 * length * math.sin(a), c + 0.14 * length * math.cos(a)),
                (c + length * math.sin(a), c - length * math.cos(a))], fill=color + (255,), width=width)

    hand(hour, c * 0.46, 15, INK)
    hand(minute, c * 0.70, 10, INK)
    hand(second, c * 0.78, 4, RED)
    d.ellipse((c - 13, c - 13, c + 13, c + 13), fill=INK + (255,))
    return img, boxes


def _calendar(spec: dict) -> tuple[Image.Image, dict]:
    w, h = SIZES["calendar"]
    img = Image.new("RGBA", (w, h), CREAM + (255,))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, 118), fill=(168, 44, 36))
    d.text((w / 2, 60), f"{spec['month_hi']} {spec['year']}", font=compose._font("ExtraBold", 74), fill=CHALK,
           anchor="mm")
    cols, cw = 7, (w - 40) / 7
    small, num = compose._font("Bold", 40), compose._font("Bold", 52)
    for k, name in enumerate(spec["weekdays"]):
        d.text((20 + cw * (k + 0.5), 148), name, font=small, fill=(168, 44, 36) if k == 0 else (90, 70, 50),
               anchor="mm")
    d.line([(20, 176), (w - 20, 176)], fill=(120, 100, 80), width=3)
    ch = 98
    cells = {}
    for day in range(1, spec["days"] + 1):
        idx = spec["first_col"] + day - 1
        row, col = divmod(idx, cols)
        x, y = 20 + cw * (col + 0.5), 176 + ch * (row + 0.5) + 6
        d.text((x, y), str(day), font=num, fill=(168, 44, 36) if col == 0 else INK, anchor="mm")
        cells[day] = (20 + cw * col, 176 + ch * row + 6, 20 + cw * (col + 1), 176 + ch * (row + 1) + 6)
    lo, hi = spec["odd"]
    a, b = cells[lo], cells[hi]
    return img, {"answer": (min(a[0], b[0]) + 4, min(a[1], b[1]) + 12, max(a[2], b[2]) - 4, max(a[3], b[3]) - 4)}


def render(kind: str, spec: dict, t: float = 0.0) -> tuple[Image.Image, dict]:
    """The card as an RGBA picture, and {"answer": (x0, y0, x1, y1)}: where its odd part is, in card pixels."""
    if kind == "timetable":
        return _timetable(spec)
    if kind == "clock":
        return _clock(spec, t)
    if kind == "calendar":
        return _calendar(spec)
    raise ValueError(f"unknown card kind {kind!r}; the kinds are {KINDS}")


def state(kind: str, t: float) -> int:
    """What changes on the card with time: a clock's second hand ticks, the other cards stand still. A plate is
    drawn again only when this changes."""
    return int(t) if kind == "clock" else 0


def _ring_stats(plate: np.ndarray, mask: np.ndarray, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Mean and spread per channel of the plate in a ring just outside the card."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * width + 1, 2 * width + 1))
    outer = cv2.dilate(mask, k)
    inner = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    ring = (outer > 0) & (inner == 0)
    if ring.sum() < 50:
        ring = outer == 0
    px = plate[ring].astype(np.float32)
    return px.mean(axis=0), px.std(axis=0)


def composite(plate: np.ndarray, card: Image.Image, quad: list[list[float]], seed: int = 0,
              mean_pull: float = 0.55, spread_pull: float = 0.4) -> np.ndarray:
    """plate (RGB uint8) with the card warped onto quad (four corners TL, TR, BR, BL as shares of the plate) and
    graded into it: per channel the card's mean moves mean_pull of the way to the mean of a ring around the quad and
    its spread spread_pull of the way to the ring's (not all the way: the text must stay readable), then film grain
    at the ring's level and a one-pixel feather. A pull of 0 leaves the card as drawn."""
    h, w = plate.shape[:2]
    dst = np.array([[x * w, y * h] for x, y in quad], np.float32)
    rgba = np.asarray(card.convert("RGBA"), np.uint8)
    ch, cw = rgba.shape[:2]
    src = np.array([[0, 0], [cw, 0], [cw, ch], [0, ch]], np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    # The box around the quad is all the warp needs to touch.
    x0, y0 = max(int(dst[:, 0].min()) - 8, 0), max(int(dst[:, 1].min()) - 8, 0)
    x1, y1 = min(int(dst[:, 0].max()) + 9, w), min(int(dst[:, 1].max()) + 9, h)
    shift = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], np.float64)
    warped = cv2.warpPerspective(rgba, shift @ m, (x1 - x0, y1 - y0), flags=cv2.INTER_AREA if cw > (x1 - x0) * 1.6
                                 else cv2.INTER_LINEAR)
    alpha = (warped[..., 3] > 127).astype(np.uint8)
    out = plate.copy()
    sub = plate[y0:y1, x0:x1]
    mean_r, std_r = _ring_stats(sub, alpha, max(6, (x1 - x0) // 14))
    inside = warped[..., :3].astype(np.float32)
    sel = alpha > 0
    mean_c, std_c = inside[sel].mean(axis=0), inside[sel].std(axis=0) + 1e-3
    gain = 1 + spread_pull * (np.clip(std_r / std_c, 0.5, 1.5) - 1)
    graded = (inside - mean_c) * gain + mean_c + mean_pull * (mean_r - mean_c)
    rng = np.random.default_rng(seed)
    graded += rng.normal(0, max(float(std_r.mean()) * 0.25, 1.5), graded.shape[:2])[..., None].astype(np.float32)
    soft = cv2.GaussianBlur(alpha.astype(np.float32), (0, 0), 0.9)[..., None]
    out[y0:y1, x0:x1] = np.clip(sub * (1 - soft) + graded * soft, 0, 255).astype(np.uint8)
    return out


def quad_area(quad: list[list[float]]) -> float:
    """Area of a quad given as shares of the plate (shoelace), as a share of the plate."""
    xs, ys = zip(*quad)
    return abs(sum(xs[i] * ys[(i + 1) % 4] - xs[(i + 1) % 4] * ys[i] for i in range(4))) / 2


def iou(a: tuple, b: tuple) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def answer_card(prev: dict, text: str, register: str, size: tuple[int, int] | None = None) -> tuple[np.ndarray, dict]:
    """The previous episode's answer as a full frame (RGB): its card on a dark panel, a red circle on the odd part,
    the answer line and Jhabbu's register line. Returns the frame and {"circle", "target", "iou"} in frame pixels."""
    W, H = size or (compose.W, compose.H)
    frame = Image.new("RGB", (W, H), (16, 22, 26))
    d = ImageDraw.Draw(frame)
    for y in range(H):
        k = 0.5 + 0.5 * y / H
        d.line([(0, y), (W, y)], fill=(round(16 * k + 8), round(24 * k + 8), round(30 * k + 8)))
    card, boxes = render(prev["kind"], prev["spec"], prev.get("t", 0.0))
    cx = round(compose.TEXT_CX * W / compose.W)  # the safe zone is not centred
    cw = min(round(W * 0.74), round(H * 0.40 * card.width / card.height))  # a tall card must leave room for the text
    ch = round(cw * card.height / card.width)
    top = round(H * 0.20)
    face = card.resize((cw, ch), Image.LANCZOS)
    frame.paste(face, (cx - cw // 2, top), face)
    s = cw / card.width
    ox, oy = cx - cw // 2, top
    x0, y0, x1, y1 = boxes["answer"]
    target = (ox + x0 * s, oy + y0 * s, ox + x1 * s, oy + y1 * s)
    padx, pady = (target[2] - target[0]) * 0.08, (target[3] - target[1]) * 0.08
    circle = (target[0] - padx, target[1] - pady, target[2] + padx, target[3] + pady)
    d.ellipse(circle, outline=RED, width=max(8, W // 120))
    y = top + ch + 56
    for line, weight, size, color in ((text, "ExtraBold", 54, CHALK), (register, "Medium", 44, (255, 190, 92))):
        d.text((cx, y), line, font=compose._fit(weight, size, line, compose.TEXT_W), fill=color, anchor="mm")
        y += 82
    return np.asarray(frame, np.uint8), {"circle": circle, "target": target, "iou": iou(circle, target),
                                         "bottom": y / H}
