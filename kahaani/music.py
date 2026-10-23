"""A dark-ambient bed written in code for each story (no samples, so no licence or Content ID claims): a low drone
that breathes, soft low pulses like a slow heartbeat, a high shimmer, and one bell struck where the twist lands.

The key is chosen from the story id, so consecutive Shorts don't sound identical.
"""
from __future__ import annotations

import hashlib
import math

import numpy as np

SR = 44100
ROOTS = (36, 38, 33, 35, 31)  # C2 D2 A1 B1 G1
PULSE_EVERY = 1.6
# A struck bell's partials (ratios to the strike tone) and how fast each dies away.
BELL = ((0.5, 1.2), (1.0, 1.6), (1.19, 2.4), (1.56, 3.2), (2.0, 3.8), (2.51, 5.0), (3.01, 6.5))


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _drone(f: float, n: int, rng) -> np.ndarray:
    t = np.arange(n) / SR
    breath = 0.65 + 0.35 * np.sin(2 * np.pi * t / 11.0 + rng.uniform(0, 6.28))
    tone = sum((0.8 / k) * np.sin(2 * np.pi * f * k * (1 + 0.0015 * d) * t + rng.uniform(0, 6.28))
               for k in (1, 2, 3) for d in (-1, 0, 1))
    fifth = 0.35 * np.sin(2 * np.pi * f * 1.5 * t + 1.0) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 17.0))
    return ((tone / 6 + fifth) * breath).astype(np.float32)


def _pulse(f: float) -> np.ndarray:
    t = np.arange(int(0.9 * SR)) / SR
    thump = np.sin(2 * np.pi * f * t * (1 + 0.6 * np.exp(-t * 18))) * np.exp(-t * 6.5)
    return (thump * np.minimum(1, t / 0.01)).astype(np.float32)


def bell(f: float, seconds: float = 6.0) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    tone = sum(np.sin(2 * np.pi * f * r * t) * np.exp(-t * d / 2.2) / (1 + i * 0.6) for i, (r, d) in enumerate(BELL))
    return (tone * np.minimum(1, t / 0.003)).astype(np.float32)


def _shimmer(n: int, rng) -> np.ndarray:
    noise = rng.standard_normal(n).astype(np.float32)
    spectrum = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    spectrum *= np.exp(-((freqs - 3200) / 900) ** 2)
    air = np.fft.irfft(spectrum, n).astype(np.float32)
    t = np.arange(n) / SR
    return air / max(np.abs(air).max(), 1e-6) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 7.0)).astype(np.float32)


def _reverb(x: np.ndarray, seconds: float = 3.5, wet: float = 0.45, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    ir = rng.standard_normal(n).astype(np.float32) * np.exp(-np.arange(n) / SR * 2.4).astype(np.float32)
    ir /= np.sqrt((ir ** 2).sum())
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:len(x)].astype(np.float32)
    return (1 - wet) * x + wet * y


def score(seconds: float, seed_text: str, bell_at: float | None = None) -> np.ndarray:
    """Stereo float32 [n, 2] at 44.1 kHz, peak -6 dBFS, with fades; the bell strikes at bell_at seconds."""
    seed = int(hashlib.sha1(seed_text.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    root = _hz(ROOTS[seed % len(ROOTS)])
    n = int(seconds * SR)
    left, right = _drone(root, n, rng), _drone(root * 1.002, n, rng)
    pulse = _pulse(root)
    for k in range(int(seconds / PULSE_EVERY) + 1):
        s = int((k * PULSE_EVERY + 0.8) * SR)
        e = min(n, s + len(pulse))
        if s < e:
            gain = 0.55 if k % 2 == 0 else 0.3
            left[s:e] += gain * pulse[:e - s]
            right[s:e] += gain * pulse[:e - s]
    air = _shimmer(n, rng) * 0.06
    left += air
    right += np.roll(air, SR // 7)
    if bell_at is not None and 0 <= bell_at < seconds:
        b = bell(_hz(ROOTS[seed % len(ROOTS)] + 36))
        s = int(bell_at * SR)
        e = min(n, s + len(b))
        left[s:e] += 0.9 * b[:e - s]
        right[s:e] += 0.75 * b[:e - s]
    left, right = _reverb(left, seed=seed), _reverb(right, seed=seed + 1)
    mix = np.stack([left, right], axis=1)
    fade_in, fade_out = min(int(1.5 * SR), n // 3), min(int(2.0 * SR), n // 3)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    mix[n - fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return (mix / max(np.abs(mix).max(), 1e-6) * 0.5).astype(np.float32)


# ---- Format M foley: every sound is made here from noise and sines, never a sample ------------------------------------
# Beds run for a length (to the end of the Short when none is given); the others are one-shots.
BEDS = ("crickets", "bulb_hum", "kerosene_hiss", "rain_tin", "angithi_crackle", "radio_static", "wire_hum")
ONE_SHOTS = ("bell", "ticket_press", "clock_tick", "page_turn", "glass_clink", "moth_tick", "signal_clank", "drip",
             "coin_jingle", "torch_click")
CUES = BEDS + ONE_SHOTS
GAIN = {"crickets": 0.10, "bulb_hum": 0.05, "kerosene_hiss": 0.05, "rain_tin": 0.16, "angithi_crackle": 0.12,
        "radio_static": 0.07, "wire_hum": 0.04, "bell": 0.5, "ticket_press": 0.9, "clock_tick": 0.6, "page_turn": 0.5,
        "glass_clink": 0.55, "moth_tick": 0.35, "signal_clank": 0.6, "drip": 0.45, "coin_jingle": 0.5,
        "torch_click": 0.6}
# The register motif: four notes, minor, unresolved (A C E D), struck on a plucked bell tone and never sung.
MOTIF_NOTES = (57, 60, 64, 62)
MOTIF_STEP = 0.55
MOTIF_GAIN = 0.14


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * SR)) / SR


def _band(n: int, lo: float, hi: float, rng) -> np.ndarray:
    """White noise kept between lo and hi Hz, peak 1."""
    spectrum = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spectrum[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spectrum, n)
    return (x / max(np.abs(x).max(), 1e-9)).astype(np.float32)


def _clicks(n: int, per_second: float, rng, rate: float = 900.0, freq: float = 2200.0) -> np.ndarray:
    """Sparse short ticks at random times (embers, drops on tin)."""
    out = np.zeros(n, np.float32)
    t = _t(0.02)
    for s in rng.integers(0, max(n - len(t), 1), int(n / SR * per_second)):
        out[s:s + len(t)] += (rng.uniform(0.3, 1.0) * np.sin(2 * np.pi * freq * rng.uniform(0.7, 1.4) * t)
                              * np.exp(-t * rate)).astype(np.float32)
    return out


def _bed(cue: str, seconds: float, rng) -> np.ndarray:
    n = int(seconds * SR)
    t = np.arange(n) / SR
    if cue == "crickets":
        out = np.zeros(n, np.float32)
        for carrier in (3900, 4300, 4700):
            chirp = (np.sin(2 * np.pi * 26 * t + rng.uniform(0, 6.28)) > 0.55) * 1.0
            burst = (np.sin(2 * np.pi * rng.uniform(1.6, 2.6) * t + rng.uniform(0, 6.28)) > 0.1) * 1.0
            out += (np.sin(2 * np.pi * carrier * t) * chirp * burst * 0.4).astype(np.float32)
        return out
    if cue == "bulb_hum":
        flutter = (1 + 0.03 * np.sin(2 * np.pi * 0.7 * t)).astype(np.float32)
        tone = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((100, 1.0), (50, 0.5), (200, 0.35), (300, 0.15)))
        return (tone * flutter / 2).astype(np.float32)
    if cue == "kerosene_hiss":
        return _band(n, 2500, 7500, rng) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.9 * t + 1.0)).astype(np.float32)
    if cue == "rain_tin":
        return 0.55 * _band(n, 700, 6500, rng) + 0.9 * _clicks(n, 90, rng, rate=700, freq=2800)
    if cue == "angithi_crackle":
        return 0.25 * _band(n, 80, 380, rng) + _clicks(n, 16, rng, rate=500, freq=1600)
    if cue == "radio_static":
        crackle = (0.5 + 0.5 * np.sin(2 * np.pi * 3.1 * t) * np.sin(2 * np.pi * 0.37 * t)).astype(np.float32)
        return _band(n, 400, 5200, rng) * crackle + 0.1 * np.sin(2 * np.pi * 1050 * t).astype(np.float32)
    if cue == "wire_hum":
        return (np.sin(2 * np.pi * 120 * t + 0.4 * np.sin(2 * np.pi * 0.5 * t)) * 0.6
                + np.sin(2 * np.pi * 1450 * t) * 0.05).astype(np.float32)
    raise KeyError(cue)


def _shot(cue: str, dur: float | None, rng) -> np.ndarray:
    if cue == "bell":
        return bell(1450.0, 2.2) * 0.8
    if cue == "ticket_press":
        t = _t(0.35)
        thud = np.sin(2 * np.pi * 70 * t * (1 + 0.5 * np.exp(-t * 30))) * np.exp(-t * 18)
        snap = _band(len(t), 1500, 5000, rng) * np.exp(-t * 90)
        return (thud + 0.6 * snap).astype(np.float32)
    if cue == "clock_tick":
        # one tick a second, a lower tock on the odd ones
        seconds = max(dur or 1.0, 0.1)
        out = np.zeros(int(seconds * SR) + SR // 4, np.float32)
        for k in range(int(math.ceil(seconds))):
            t = _t(0.05)
            f = 2100 if k % 2 == 0 else 1700
            s = int(k * SR)
            out[s:s + len(t)] += (np.sin(2 * np.pi * f * t) * np.exp(-t * 110)
                                  + 0.4 * _band(len(t), 1000, 4000, rng) * np.exp(-t * 140)).astype(np.float32)
        return out
    if cue == "page_turn":
        n = int(0.45 * SR)
        swell = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
        return (_band(n, 1800, 7000, rng) * swell * (0.7 + 0.3 * rng.standard_normal(n).clip(-1, 1))).astype(np.float32)
    if cue == "glass_clink":
        t = _t(0.45)
        return ((np.sin(2 * np.pi * 3150 * t) + 0.6 * np.sin(2 * np.pi * 4720 * t) + 0.3 * np.sin(2 * np.pi * 6100 * t))
                * np.exp(-t * 11) * 0.5).astype(np.float32)
    if cue == "moth_tick":
        t = _t(0.03)
        return (np.sin(2 * np.pi * 3300 * t) * np.exp(-t * 260)).astype(np.float32)
    if cue == "signal_clank":
        t = _t(0.9)
        tone = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d)
                   for f, a, d in ((310, 1.0, 5.0), (467, 0.7, 7.0), (905, 0.5, 9.0), (1380, 0.3, 14.0)))
        return (tone + 0.5 * _band(len(t), 800, 4000, rng) * np.exp(-t * 60)).astype(np.float32) * 0.6
    if cue == "drip":
        t = _t(0.18)
        return (np.sin(2 * np.pi * (900 + 1100 * np.exp(-t * 55)) * t) * np.exp(-t * 28)).astype(np.float32)
    if cue == "coin_jingle":
        out = np.zeros(int(0.5 * SR), np.float32)
        for k, f in enumerate((5200, 6100, 4700)):
            t = _t(0.16)
            s = int(k * 0.07 * SR)
            out[s:s + len(t)] += (np.sin(2 * np.pi * f * t) * np.exp(-t * 28) * 0.6).astype(np.float32)
        return out
    if cue == "torch_click":
        out = np.zeros(int(0.3 * SR), np.float32)
        for s, f in ((0, 1250), (int(0.16 * SR), 1050)):
            t = _t(0.03)
            out[s:s + len(t)] += (np.sin(2 * np.pi * f * t) * np.exp(-t * 150)).astype(np.float32)
        return out
    raise KeyError(cue)


def motif(seconds: float = MOTIF_STEP * 4 + 2.0) -> np.ndarray:
    """The four-note register motif as a mono float32 at 44.1 kHz: each note a plucked bell-like tone (a sine, its
    octave and a slightly sharp twelfth, quickly softening), in a small room. Never sung, never a voice."""
    out = np.zeros(int(seconds * SR), np.float32)
    for k, midi in enumerate(MOTIF_NOTES):
        f = _hz(midi)
        t = _t(1.8)
        note = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 2.5)
                + 0.12 * np.sin(2 * np.pi * 3.01 * f * t) * np.exp(-t * 4)) * np.exp(-t * 1.9) * np.minimum(1, t / 0.004)
        s = int(k * MOTIF_STEP * SR)
        e = min(len(out), s + len(note))
        out[s:e] += note[:e - s].astype(np.float32) * (1.0 if k < 3 else 0.8)
    return _reverb(out, seconds=2.0, wet=0.35, seed=7)


def foley(cues: list[dict], seconds: float, seed: int | str = 0) -> tuple[np.ndarray, np.ndarray]:
    """(foley, motif): two stereo float32 [n, 2] tracks at 44.1 kHz, both un-normalised (a loudness stage follows).
    cues: [{"cue", "at", "dur"}]; a bed with no dur runs to the end. A "motif" cue places the motif into the second
    track, everything else into the first. Each cue gets its own pan and noise from the seed."""
    if isinstance(seed, str):
        seed = int(hashlib.sha1(seed.encode()).hexdigest()[:8], 16)
    n = int(seconds * SR)
    bed, mo = np.zeros((n, 2), np.float32), np.zeros((n, 2), np.float32)
    for i, c in enumerate(cues):
        rng = np.random.default_rng(seed + 31 * i)
        at = int(max(c["at"], 0) * SR)
        if at >= n:
            continue
        name = c["cue"]
        if name == "motif":
            x, track, gain = motif(), mo, MOTIF_GAIN
        elif name in BEDS:
            length = c.get("dur") or (seconds - c["at"])
            x = _bed(name, min(length, seconds - c["at"]) + 0.01, rng)
            fade = min(int(0.25 * SR), len(x) // 3)
            x[:fade] *= np.linspace(0, 1, fade)
            x[len(x) - fade:] *= np.linspace(1, 0, fade)
            track, gain = bed, GAIN[name]
        elif name in ONE_SHOTS:
            x, track, gain = _shot(name, c.get("dur"), rng), bed, GAIN[name]
        else:
            raise KeyError(f"no foley cue {name!r}; the cues are {CUES + ('motif',)}")
        pan = rng.uniform(0.35, 0.65) if name in BEDS or name == "motif" else rng.uniform(0.25, 0.75)
        e = min(n, at + len(x))
        track[at:e, 0] += gain * (1 - pan) * 1.4 * x[:e - at]
        track[at:e, 1] += gain * pan * 1.4 * x[:e - at]
    return bed, mo
