from types import SimpleNamespace

import pytest

from kahaani import config, store


class Gh:
    def __init__(self, code=0, make=None):
        self.calls, self.code, self.make = [], code, make

    def __call__(self, args, **kw):
        self.calls.append(args)
        if self.make:
            for name in store.FILES:
                (self.make / name).write_text("x")
        return SimpleNamespace(returncode=self.code, stdout="", stderr="HTTP 404")


def test_put_creates_a_draft_release(tmp_path):
    for name in store.FILES:
        (tmp_path / name).write_text("x")
    gh = Gh()
    assert store.put("kc-1", tmp_path, "कुआँ! 😨", run=gh) == "ready-kc-1"
    args = gh.calls[0]
    assert args[:4] == ["gh", "release", "create", "ready-kc-1"] and "--draft" in args
    assert args[-2:] == ["--repo", config.REPO]
    assert [a for a in args if a.endswith(".mp4")] == [str(tmp_path / "short.mp4")]


def test_put_refuses_an_incomplete_short(tmp_path):
    with pytest.raises(FileNotFoundError):
        store.put("kc-1", tmp_path, "t", run=Gh())


def test_fetch_and_drop(tmp_path):
    folder = tmp_path / "f"
    folder.mkdir()
    gh = Gh(make=folder)
    assert store.fetch("kc-1", folder, run=gh) == folder
    assert gh.calls[0][:4] == ["gh", "release", "download", "ready-kc-1"] and "--clobber" in gh.calls[0]
    store.drop("kc-1", run=gh)
    assert gh.calls[1][:5] == ["gh", "release", "delete", "ready-kc-1", "--yes"]


def test_a_failed_gh_call_raises():
    with pytest.raises(RuntimeError, match="HTTP 404"):
        store.drop("kc-1", run=Gh(code=1))
