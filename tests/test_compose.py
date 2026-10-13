import json
import subprocess
from types import SimpleNamespace

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont, features

from kahaani import compose
from kahaani.spec import Beat, Story

from .conftest import story_dict

SAMPLE = "क्षत्रिय श्री दृष्टि"


def _ink(layout) -> np.ndarray:
    font = ImageFont.truetype(str(compose.FONTS / compose.WEIGHTS["Bold"]), 80, layout_engine=layout)
    img = Image.new("L", (900, 140), 0)
    ImageDraw.Draw(img).text((10, 10), SAMPLE, font=font, fill=255)
    return np.asarray(img)


def test_devanagari_is_shaped_with_raqm():
    assert features.check("raqm")
    assert compose._font("Bold", 80).layout_engine == ImageFont.Layout.RAQM
    assert not np.array_equal(_ink(ImageFont.Layout.RAQM), _ink(ImageFont.Layout.BASIC))


def test_the_title_emoji_is_dropped_from_the_headline():
    assert compose.drawable("कुएँ ने क्या लिया? 😨", "ExtraBold") == "कुएँ ने क्या लिया?"
    assert compose._headline_layer(story_dict()["title"])[1].shape[1] <= compose.W


def test_captions_break_at_hindi_full_stops_and_three_words():
    words = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.25}
             for i, t in enumerate("धनीराम हँसा। परछाईं से किसका पेट भरता है?".split())]
    chunks = compose._chunks(words, lambda text: len(text) * 40)
    assert [" ".join(w["text"] for w in c) for c in chunks] == ["धनीराम हँसा।", "परछाईं से किसका", "पेट भरता है?"]


def test_label_and_end_card_carry_the_disclosure_and_no_asks():
    assert compose.AI_LABEL == "AI चित्र और आवाज़ · काल्पनिक कहानी"
    assert "काल्पनिक" in compose.END_LINE and "AI" in compose.END_LINE
    for text in (compose.AI_LABEL, compose.END_LINE, compose.config.TAGLINE):
        assert not any(ask in text for ask in ("लाइक", "सब्सक्राइब", "शेयर", "फॉलो"))
    assert all(layer[1].shape[1] <= compose.W for layer in compose._end_layers())


def test_the_bell_rings_just_before_the_twist():
    story = Story.from_dict(story_dict())
    spans = [[i * 5.0, i * 5.0 + 4.5] for i in range(len(story.beats))]
    assert compose.bell_time(story, spans) == spans[story.twist_beat - 1][0] - compose.BELL_LEAD


def test_camera_moves_with_numpy_scalars():
    size = (np.int64(compose.H + 120), np.int64(compose.W + 120))
    plate = SimpleNamespace(pw=size[1], ph=size[0], rgb=np.full((*size, 3), 90, np.uint8),
                            depth=np.zeros(size, np.float32))
    frame = compose.Camera().shoot(plate, np.float64(0.4), compose.MOTIONS[1], punch=np.float64(0.02))
    assert frame.shape == (compose.H, compose.W, 3) and frame.dtype == np.uint8 and frame.mean() > 80


def test_a_short_story_renders(tmp_path, monkeypatch):
    monkeypatch.setattr(compose.depth, "estimate", lambda img, cache=None: np.tile(
        np.linspace(0, 1, img.height, dtype=np.float32)[:, None], (1, img.width)))
    pictures = []
    for i, color in enumerate([(30, 50, 80), (90, 60, 30), (20, 70, 60)]):
        path = tmp_path / f"beat{i:02d}.jpg"
        Image.new("RGB", (576, 1024), color).save(path)
        pictures.append(path)
    texts = ["कुआँ बोला।", "धनीराम हँसा।", "परछाईं चली गई।"]
    story = Story(id="kc-smoke", premise="p003", title="कुएँ ने क्या लिया? 😨", hook=texts[0],
                  beats=[Beat(text=t, scene="s") for t in texts], cast=[], subgenre="jadui-inaam",
                  ending="twist-reveal", twist_beat=2, description="d")
    sr = 24000
    t = np.arange(int(3.0 * sr)) / sr
    sf.write(tmp_path / "narration.wav", (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr)
    words = [{"text": w, "start": 0.35 + k * 0.4, "end": 0.7 + k * 0.4, "beat": k // 2}
             for k, w in enumerate(" ".join(texts).split())]
    timing = {"duration": 3.0, "words": words, "beats": [[0.35, 1.1], [1.1, 2.0], [2.0, 3.0]]}
    stats = compose.render(story, timing, pictures, tmp_path)
    assert stats == {"duration": 5.4, "frames": 162, "pictures": 3, "fps": 30, "size": [1080, 1920]}
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                                       "-of", "json", str(tmp_path / "short.mp4")], capture_output=True,
                                      text=True, check=True).stdout)
    assert {s["codec_type"] for s in probe["streams"]} == {"video", "audio"}
    assert abs(float(probe["format"]["duration"]) - 5.4) < 0.15
