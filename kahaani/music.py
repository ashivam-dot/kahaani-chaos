"""A dark-ambient bed written in code for each story (no samples, so no licence or Content ID claims): a low drone
that breathes, soft low pulses like a slow heartbeat, a high shimmer, and one bell struck where the twist lands.

The key is chosen from the story id, so consecutive Shorts don't sound identical.
"""
from __future__ import annotations

import hashlib

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
