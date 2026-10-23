import json
import re

from kahaani import branding, look, vision


def test_the_about_text_says_what_is_fiction_and_what_is_ai():
    assert branding.TITLE in branding.DESCRIPTION
    assert "काल्पनिक" in branding.DESCRIPTION and "AI" in branding.DESCRIPTION
    assert "#सन्नाटपुर" in branding.DESCRIPTION
    assert len(branding.DESCRIPTION) < 1000 and len(branding.KEYWORDS) < 500
    assert not vision.CHILD_WORDS.search(branding.DESCRIPTION + " " + branding.KEYWORDS)


def test_the_plans_paint_every_seed_at_the_kind_size_with_nobody_in_it(tmp_path):
    for path in branding.plans(tmp_path):
        plan = json.loads(path.read_text(encoding="utf-8"))
        spec = branding.ART[path.stem.removesuffix("-plan")]
        assert (plan["width"], plan["height"]) == (spec["width"], spec["height"])
        assert [b["seed"] for b in plan["beats"]] == spec["seeds"]
        for beat in plan["beats"]:
            assert look.NOBODY in beat["prompt"]
            assert not re.search(r"9:16", beat["prompt"])


def test_compose_names_files_by_seed_slot(tmp_path):
    from PIL import Image

    (tmp_path / "art" / "banner").mkdir(parents=True)
    (tmp_path / "art" / "avatar").mkdir(parents=True)
    Image.new("RGB", (1536, 864), (20, 30, 60)).save(tmp_path / "art" / "banner" / "beat01.png")
    Image.new("RGB", (1024, 1024), (20, 30, 60)).save(tmp_path / "art" / "avatar" / "beat00.png")
    made = branding.compose(tmp_path / "art", tmp_path / "out")
    assert sorted(p.name for p in made) == ["avatar-0.jpg", "banner-1.jpg"]
    assert Image.open(tmp_path / "out" / "banner-1.jpg").size == branding.SIZE
    assert Image.open(tmp_path / "out" / "avatar-0.jpg").size == (800, 800)


class _Call:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class _Api:
    def __init__(self, channel):
        self.channel, self.updates = channel, []

    def channels(self):
        return self

    def list(self, **_):
        return _Call({"items": [{"id": "UC1", "snippet": {"title": "Kahaani Chaos"},
                                 "brandingSettings": {"channel": dict(self.channel)}}]})

    def update(self, part, body):
        self.updates.append(body)
        self.channel = body["brandingSettings"]["channel"]
        return _Call({})


def test_apply_drops_the_read_only_fields_and_reads_back(monkeypatch):
    from kahaani import youtube

    api = _Api({"title": "Kahaani Chaos", "unsubscribedTrailer": "x", "country": "IN", "description": "old"})
    monkeypatch.setattr(youtube, "identity", lambda a: {"id": "UC1", "snippet": {"title": "Kahaani Chaos"}})
    shown = branding.apply(api, None, write=False)
    assert shown["changed"] == ["description", "keywords"] and not api.updates
    done = branding.apply(api, None, write=True)
    sent = api.updates[0]["brandingSettings"]["channel"]
    assert "title" not in sent and "unsubscribedTrailer" not in sent and sent["country"] == "IN"
    assert done["readback_ok"] is True
