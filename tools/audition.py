"""Audition Gemini TTS narrators on one story passage, then score each take: UTMOS22 naturalness, harshness
(2-5 kHz share), brightness, median pitch and pitch variation, words per minute and Whisper CER.

usage: python tools/audition.py OUT_DIR [VOICE ...]   (needs GEMINI_API_KEY)
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import requests
import soundfile as sf

VOICES = ["Charon", "Enceladus", "Algenib", "Gacrux", "Achernar", "Iapetus", "Orus"]
MODELS = ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts", "gemini-3.1-flash-tts-preview",
          "gemini-2.5-flash-preview-tts")
DIRECTION = ("Narrate this Hindi folk-mystery story to one listener like a storyteller by a lantern at night: low, "
             "intimate and suspenseful, with short pauses between sentences and a longer pause before the last two "
             "lines. Never theatrical, no shouting. About 150 words a minute. Speak only the transcript.")
TEXT = ("उस रात गाँव के कुएँ से किसी ने रामू का नाम पुकारा। आवाज़ उसकी माँ की थी, पर माँ तो दस साल पहले गुज़र चुकी थी। "
        "दादी ने कहा था, कुएँ की आवाज़ का जवाब कभी मत देना। रामू ने लालटेन उठाई और धीरे से झाँका। "
        "पानी में उसका अपना चेहरा था, पर वो मुस्कुरा रहा था। रामू नहीं मुस्कुरा रहा था। "
        "तभी पीछे से आवाज़ आई, बेटा, घर चल। रामू ने मुड़कर देखा, तो वहाँ कोई नहीं था।")
INTERACTIONS = "https://generativelanguage.googleapis.com/v1beta/interactions"
API = "https://generativelanguage.googleapis.com/v1beta/models"


def request(model: str, voice: str) -> tuple[str, dict]:
    if model.startswith("gemini-3.8-"):
        return INTERACTIONS, {
            "model": model, "store": False,
            "input": [{"type": "user_input", "content": [{"type": "text", "text": TEXT,
                       "annotations": [{"type": "speech_metadata", "style": DIRECTION}]}]}],
            "response_format": {"type": "audio", "mime_type": "audio/wav"},
            "generation_config": {"speech_config": [{"voice": voice}]}}
    return f"{API}/{model}:generateContent", {
        "contents": [{"parts": [{"text": f"{DIRECTION}\n\nTRANSCRIPT:\n{TEXT}"}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}


def audio(data: dict) -> tuple[np.ndarray, int]:
    if "steps" in data:
        part = next(p for s in data["steps"] if s.get("type") == "model_output"
                    for p in s.get("content", []) if p.get("type") == "audio")
        raw, mime = base64.b64decode(part["data"]), part.get("mime_type", "")
    else:
        part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
        raw, mime = base64.b64decode(part["data"]), part.get("mimeType", "")
    if raw[:4] == b"RIFF":
        x, sr = sf.read(io.BytesIO(raw), dtype="float32")
        return (x.mean(axis=1) if x.ndim > 1 else x), sr
    sr = next((int(p[5:]) for p in mime.replace(" ", "").split(";") if p.startswith("rate=")), 24000)
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0, sr


spent: set[str] = set()


def take(voice: str) -> tuple[np.ndarray, int, str]:
    key = os.environ["GEMINI_API_KEY"]
    errors = []
    for model in [m for m in MODELS if m not in spent]:
        url, body = request(model, voice)
        for attempt in range(3):
            r = requests.post(url, headers={"x-goog-api-key": key}, json=body, timeout=300)
            if r.status_code == 200:
                x, sr = audio(r.json())
                return x, sr, model
            errors.append(f"{model} {r.status_code}")
            if r.status_code == 429 and "PerDay" not in r.text and attempt < 2:
                time.sleep(40)
                continue
            if r.status_code in (404, 429) or r.status_code == 400:
                spent.add(model)
            break
    raise RuntimeError(f"{voice}: " + "; ".join(errors))


def norm(s: str) -> str:
    s = re.sub(r"[^\u0900-\u097F ]", " ", unicodedata.normalize("NFC", s)).replace("\u093c", "")
    return "".join(s.split())


def cer(ref: str, hyp: str) -> float:
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev = cur
    return d[len(h)] / max(1, len(r))


def band_share(x: np.ndarray, sr: int, lo: float, hi: float) -> float:
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / sr)
    return spec[(f >= lo) & (f < hi)].sum() / max(spec[(f >= 80) & (f < 8000)].sum(), 1e-12)


def timbre(x: np.ndarray, sr: int) -> tuple[float, float]:
    frame, harsh, cent = int(0.04 * sr), [], []
    for i in range(0, len(x) - frame, frame):
        seg = x[i:i + frame]
        if np.sqrt(np.mean(seg ** 2)) < 0.02:
            continue
        harsh.append(band_share(seg, sr, 2000, 5000))
        spec = np.abs(np.fft.rfft(seg * np.hanning(frame)))
        f = np.fft.rfftfreq(frame, 1 / sr)
        cent.append((spec * f).sum() / max(spec.sum(), 1e-12))
    return float(np.mean(harsh)), float(np.mean(cent))


def main(out: str, voices: list[str]) -> None:
    import librosa
    import torch
    from faster_whisper import WhisperModel

    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = {}
    for v in voices:
        try:
            x, sr, model = take(v)
        except Exception as exc:
            print(f"skip {exc}"[:300])
            continue
        loud = np.flatnonzero(np.abs(x) > 0.01 * np.abs(x).max())
        x = x[max(loud[0] - 1200, 0):loud[-1] + 1200]
        sf.write(out_dir / f"{v}.wav", x, sr)
        made[v] = (x, sr, model)
        time.sleep(6)
    utmos = torch.hub.load("tarepan/SpeechMOS:v1.2.0", "utmos22_strong", trust_repo=True)
    asr = WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")
    words = len(TEXT.split())
    rows = []
    for v, (x, sr, model) in made.items():
        x16 = librosa.resample(x, orig_sr=sr, target_sr=16000)
        mos = float(utmos(torch.from_numpy(x16).unsqueeze(0), 16000).item())
        harsh, bright = timbre(x, sr)
        f0, voiced, _ = librosa.pyin(x16, fmin=60, fmax=350, sr=16000, frame_length=1024)
        f0 = f0[voiced & ~np.isnan(f0)]
        semis = 12 * np.log2(f0 / np.median(f0)) if len(f0) > 10 else np.zeros(1)
        heard = " ".join(s.text for s in asr.transcribe(str(out_dir / f"{v}.wav"), language="hi")[0])
        dur = len(x) / sr
        rows.append({"voice": v, "model": model, "utmos": round(mos, 2), "seconds": round(dur, 1),
                     "wpm": round(60 * words / dur), "harsh_2_5k": round(harsh, 3), "brightness_hz": round(bright),
                     "f0_hz": round(float(np.median(f0)) if len(f0) else 0), "pitch_var_semitones": round(float(np.std(semis)), 2),
                     "cer": round(cer(TEXT, heard), 3)})
    rows.sort(key=lambda r: -r["utmos"])
    (out_dir / "scores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:] or VOICES)
