"""Polite downloads for open weights and binaries: a contact User-Agent and a .part file renamed only when complete."""
from __future__ import annotations

from pathlib import Path

import requests

from . import config

USER_AGENT = f"kahaani-chaos/0.1 (+{config.SITE}; {config.CONTACT})"


def download(url: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    with requests.get(url, stream=True, timeout=60, headers={"User-Agent": USER_AGENT}) as r:
        r.raise_for_status()
        with part.open("wb") as fh:
            for chunk in r.iter_content(1 << 22):
                fh.write(chunk)
    part.rename(path)
    return path
