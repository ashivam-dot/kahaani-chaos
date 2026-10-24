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
    assert compose._headline_layer(story_dict()["title"])[1].shape[1] <= compose.TEXT_W


def test_the_hook_strip_is_inside_its_height_band_and_the_safe_zone():
    for strip in ("बिना पैडल जली लाइट", "छत", story_dict()["title"]):
        rgb, alpha = compose._strip_layer(strip)
        share = alpha.shape[0] / compose.H
        assert compose.STRIP_SHARE[0] <= share <= compose.STRIP_SHARE[1], (strip, share)
        assert alpha.shape[1] <= compose.TEXT_W
        assert compose.STRIP_TOP * compose.H + alpha.shape[0] <= compose.SAFE_BOTTOM * compose.H


def test_text_stays_clear_of_the_shorts_ui():
    assert compose.TEXT_CX + compose.TEXT_W // 2 <= compose.W * compose.SAFE_RIGHT
    assert compose.TEXT_CX - compose.TEXT_W // 2 >= compose.SIDE
    assert compose.CAPTION_Y < compose.SAFE_BOTTOM
    for ending in ("", "loop-back", "register-line", "open-question"):
        layers = compose._end_layers(ending)
        assert 3 <= len(layers) <= 4 and all(layer[1].shape[1] <= compose.TEXT_W for layer in layers)
        bottom = compose.END_AT[len(layers) - 1] * compose.H + layers[-1][1].shape[0]
        assert bottom <= compose.SAFE_BOTTOM * compose.H


def _frame(level, spread):
    rng = np.random.default_rng(0)
    gray = np.clip(rng.normal(level, spread, (compose.H // 8, compose.W // 8, 1)), 0, 255)
    return np.repeat(gray, 3, axis=2).astype(np.uint8)


def test_picture_checks_have_floor_and_ceiling():
    ok = _frame(128, 70)
    assert compose.problems([120.0] * 10, set(), ok, 10, 10) == []
    assert any("mean luma" in p for p in compose.problems([120.0], set(), _frame(40, 30), 1, 1))
    assert any("mean luma" in p for p in compose.problems([120.0], set(), _frame(220, 30), 1, 1))
    assert any("RMS contrast" in p for p in compose.problems([120.0], set(), _frame(128, 5), 1, 1))
    harsh = np.zeros_like(ok)
    harsh[::2] = 255  # black and white stripes: RMS contrast 0.5
    assert any("RMS contrast" in p for p in compose.problems([120.0], set(), harsh, 1, 1))


def test_a_blink_outside_a_cut_and_a_wrong_frame_count_hold():
    dip = [120.0, 120.0, 60.0, 120.0]
    assert any("blinks" in p for p in compose.problems(dip, set(), _frame(128, 70), 4, 4))
    assert compose.problems(dip, {2}, _frame(128, 70), 4, 4) == []
    assert any("frames, expected" in p for p in compose.problems(dip, {2}, _frame(128, 70), 4, 7))
    assert compose.problems(dip, {2}, _frame(128, 70), 4, 5) == []


def test_audio_checks_have_floor_and_ceiling():
    assert compose.audio_problems({"lufs": -14.2, "true_peak": -1.6}, -26.0) == []
    assert compose.audio_problems({"lufs": -16.0, "true_peak": -1.6}, -26.0)
    assert compose.audio_problems({"lufs": -12.0, "true_peak": -1.6}, -26.0)
    assert compose.audio_problems({"lufs": -14.0, "true_peak": -0.4}, -26.0)
    assert compose.audio_problems(None)


def test_a_loud_or_unmeasured_music_bed_holds():
    ok = {"lufs": -14.0, "true_peak": -1.6}
    assert any("music bed is -18.0" in p for p in compose.audio_problems(ok, -18.0))
    assert any("music bed" in p for p in compose.audio_problems(ok, None))
    # The bed is measured before loudnorm and moved by the gain loudnorm gave the whole mix.
    assert compose.bed_level({"bed": -30.0, "premix": -20.0}, ok) == -24.0
    assert compose.bed_level({"bed": None, "premix": -20.0}, ok) is None
    assert compose.bed_level(None, ok) is None


def test_an_uncounted_frame_total_holds():
    assert any("could not be counted" in p for p in compose.problems([120.0], set(), _frame(128, 70), 1, None))


def test_text_outside_the_safe_area_or_a_wrong_strip_holds():
    H, W = compose.H, compose.W
    first = np.zeros((H, W), bool)
    first[round(H * 0.05):round(H * 0.20), 200:800] = True  # a 15% strip in the top third
    assert compose.text_problems(first, [], 100) == []
    low = first.copy()
    low[round(H * 0.80), 400] = True
    assert any("below 75%" in p for p in compose.text_problems(first, [low], 100))
    right = first.copy()
    right[900, W - 20] = True
    assert any("right 12%" in p for p in compose.text_problems(right, [], 100))
    thin = np.zeros((H, W), bool)
    thin[100:140, 200:800] = True
    assert any("of the height" in p for p in compose.text_problems(thin, [], 100))
    deep = np.zeros((H, W), bool)
    deep[round(H * 0.20):round(H * 0.40), 200:800] = True
    assert any("top third" in p for p in compose.text_problems(deep, [], 100))
    assert any("no hook strip" in p for p in compose.text_problems(np.zeros((H, W), bool), [], 100))


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
    assert all(layer[1].shape[1] <= compose.TEXT_W for layer in compose._end_layers())


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


def test_exposure_calibrates_after_grade_and_hook_without_pumping():
    size = (compose.H + 120, compose.W + 120)
    ramp = np.linspace(6, 136, size[0], dtype=np.float32)[:, None, None]
    rgb = np.broadcast_to(ramp, (*size, 3)).astype(np.uint8).copy()
    rgb[size[0] // 3:size[0] // 2, size[1] // 3:2 * size[1] // 3] = 255  # a practical light
    plate = SimpleNamespace(pw=size[1], ph=size[0], base=rgb, rgb=rgb, depth=np.zeros(size, np.float32))
    plate.lift = lambda gamma: compose.Plate.lift(plate, gamma)
    camera, grade = compose.Camera(), compose.Grade(seed=1)
    strip = compose._strip_layer("बिना पैडल जलती लाइट")
    label = compose._label_layer()
    shot = {"plate": plate, "motion": compose.MOTIONS[0]}

    def overlays(frame):
        compose._blit(frame, strip, compose.TEXT_CX - strip[1].shape[1] // 2,
                      round(compose.H * compose.STRIP_TOP))
        compose._blit(frame, label, *compose.LABEL_AT)

    def finished(t):
        frame = grade.apply(camera.shoot(plate, t, compose.MOTIONS[0], 0.06 if t == 0 else 0), 0)
        overlays(frame)
        return frame

    assert any("mean luma" in p for p in compose.problems([90], set(), finished(0), 1, 1))
    gamma = compose._expose_hook(shot, camera, grade, strip, label)
    assert min(compose.HOOK_GAMMAS) <= gamma < 1
    assert compose.problems([90], set(), finished(0), 1, 1) == []
    corrected = plate.rgb.copy()
    for t in (0.2, 0.6, 1.0, 0.0):
        finished(t)
    assert np.array_equal(plate.rgb, corrected)
    # An opening already inside the gate is not graded again.
    plate.base = corrected
    assert compose._expose_hook(shot, camera, grade, strip, label) == 1.0
    assert np.array_equal(plate.rgb, corrected)


def test_a_short_story_renders(tmp_path, monkeypatch):
    monkeypatch.setattr(compose.depth, "estimate", lambda img, cache=None: np.tile(
        np.linspace(0, 1, img.height, dtype=np.float32)[:, None], (1, img.width)))
    pictures = []
    rng = np.random.default_rng(1)
    ramp = np.linspace(15, 240, 1024)[:, None, None]
    for i, tint in enumerate([(1.0, 0.9, 0.8), (0.9, 1.0, 0.9), (0.8, 0.9, 1.0)]):
        path = tmp_path / f"beat{i:02d}.jpg"
        img = np.clip(ramp * np.array(tint) + rng.normal(0, 40, (1024, 576, 1)), 0, 255).astype(np.uint8)
        Image.fromarray(img).save(path)
        pictures.append(path)
    texts = ["साइकिल की लाइट जली।", "झब्बू हँसे।", "रोशनी रुक गई।"]
    story = Story(id="kc-smoke", premise="e01", title="साइकिल रोकी… और उसकी लाइट बिना पैडल के जल उठी! 🚲",
                  hook=texts[0], beats=[Beat(text=t, scene="s") for t in texts], cast=[], subgenre="confessed-lie",
                  ending="register-line", twist_beat=2, description="d", hook_strip="बिना पैडल जली लाइट")
    sr = 24000
    t = np.arange(int(3.0 * sr)) / sr
    sf.write(tmp_path / "narration.wav", (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sr)
    words = [{"text": w, "start": 0.35 + k * 0.4, "end": 0.7 + k * 0.4, "beat": k // 2}
             for k, w in enumerate(" ".join(texts).split())]
    timing = {"duration": 3.011, "words": words, "beats": [[0.35, 1.1], [1.1, 2.0], [2.0, 3.011]]}
    stats = compose.render(story, timing, pictures, tmp_path)
    runtime = stats.pop("runtime")
    assert stats == {"duration": 5.41, "frames": 163, "pictures": 3, "fps": 30, "size": [1080, 1920]}
    assert abs(runtime - 5.4) < 0.1
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                                       "-of", "json", str(tmp_path / "short.mp4")], capture_output=True,
                                      text=True, check=True).stdout)
    assert {s["codec_type"] for s in probe["streams"]} == {"video", "audio"}
    assert abs(float(probe["format"]["duration"]) - 5.4) < 0.15
    checks = json.loads((tmp_path / "picture-checks.json").read_text(encoding="utf-8"))
    assert checks["problems"] == [] and checks["frames"] == 163
    assert compose.count_frames(tmp_path / "short.mp4") == 163
    assert compose.LUFS[0] <= checks["loudness"]["lufs"] <= compose.LUFS[1]


def test_a_dim_night_hook_is_lifted_until_frame_0_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(compose.depth, "estimate", lambda img, cache=None: np.zeros((img.height, img.width),
                                                                                    np.float32))
    path = tmp_path / "beat00.jpg"
    night = np.clip(np.linspace(10, 110, 1024)[:, None, None] * np.ones((1, 576, 3)), 0, 255).astype(np.uint8)
    night[400:440, 260:320] = 255
    Image.fromarray(night).save(path)
    cam, grade = compose.Camera(), compose.Grade(seed=1)
    strip, label = compose._strip_layer("बिना पैडल जली लाइट"), compose._label_layer()
    shot = {"plate": compose.Plate(path), "motion": compose.MOTIONS[0]}
    gamma = compose._expose_hook(shot, cam, grade, strip, label)
    assert gamma < 1.0 and shot["plate"].rgb.mean() > shot["plate"].base.mean()
    assert shot["plate"].rgb.max() == shot["plate"].base.max()
    Image.fromarray(np.full((1024, 576, 3), 150, np.uint8)).save(tmp_path / "bright.jpg")
    bright = {"plate": compose.Plate(tmp_path / "bright.jpg"), "motion": compose.MOTIONS[0]}
    assert compose._expose_hook(bright, cam, grade, strip, label) == 1.0


def test_real_fan_hook_restores_contrast_with_one_bounded_plate_grade(tmp_path, monkeypatch):
    from pathlib import Path
    from kahaani import aiart
    root = Path(__file__).resolve().parents[1] / '.github/replay/sannatpur-fan-e09-repair'
    story = Story.load(root.with_suffix('.json'))
    monkeypatch.setattr(compose.depth, 'estimate', lambda img, cache=None: np.zeros(
        (img.height, img.width), np.float32))  # opening frame has no depth displacement
    image = tmp_path / 'beat00.jpg'
    aiart._prepare(root / 'art/beat00.png', image)
    plate, cam = compose.Plate(image), compose.Camera()
    grade = compose.Grade(seed=len(story.id))
    strip, label = compose._strip_layer(story.hook_strip), compose._label_layer()
    shot = {'plate': plate, 'motion': compose.MOTIONS[0]}
    compose._expose_hook(shot, cam, grade, strip, label)
    assert 1 < plate.hook_contrast <= max(compose.HOOK_CONTRASTS)
    assert plate.hook_new_clip <= compose.HOOK_NEW_CLIP_LIMIT
    saved = plate.rgb.copy()
    frame = grade.apply(cam.shoot(plate, 0, shot['motion'], 0.06), 0)
    compose._blit(frame, strip, compose.TEXT_CX - strip[1].shape[1] // 2, round(compose.H * compose.STRIP_TOP))
    compose._blit(frame, label, *compose.LABEL_AT)
    assert not compose.problems([float(frame.mean())], set(), frame, 1, 1)
    for t in (0.2, 0.6, 1.0):
        grade.apply(cam.shoot(plate, t, shot['motion']), 0)
    assert np.array_equal(saved, plate.rgb)


def test_a_dark_short_is_held(tmp_path, monkeypatch):
    monkeypatch.setattr(compose.depth, "estimate", lambda img, cache=None: np.zeros((img.height, img.width),
                                                                                    np.float32))
    path = tmp_path / "beat00.jpg"
    Image.new("RGB", (576, 1024), (4, 4, 6)).save(path)
    story = Story(id="kc-dark", premise="e01", title="t", hook="साइकिल", beats=[Beat(text="साइकिल", scene="s")],
                  cast=[], subgenre="", ending="register-line", twist_beat=1, description="d", hook_strip="")
    sr = 24000
    sf.write(tmp_path / "narration.wav", np.zeros(sr, np.float32), sr)
    timing = {"duration": 1.0, "words": [{"text": "साइकिल", "start": 0.2, "end": 0.8, "beat": 0}],
              "beats": [[0.2, 1.0]]}
    import pytest

    with pytest.raises(compose.ComposeHold, match="hold: picture and sound checks: frame 0"):
        compose.render(story, timing, [path], tmp_path)
