"""What a story Short is made of: the spoken beats with one painted scene each, the cast sheet and the metadata.

The F1 micro-entry fields (format onwards) default to empty so stories saved before the Sannatpur relaunch still
load."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Beat:
    text: str
    scene: str
    # Who is in this beat's painting and how they look right now: [{"name", "expression"}].
    people: list[dict] = field(default_factory=list)
    pause_after: float = 0.35


@dataclass
class Story:
    id: str
    premise: str
    title: str
    hook: str
    beats: list[Beat]
    # The cast sheet: [{"id", "name", "look"}], one fixed English look per character (from bible/cast.yaml) for
    # every painting.
    cast: list[dict]
    subgenre: str
    ending: str
    twist_beat: int  # 1-based; in F1 the turn, where the trio realises the rule
    description: str
    motifs: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    writer: dict = field(default_factory=dict)
    format: str = ""
    hook_strip: str = ""  # 3-5 Hindi words painted over frame 0
    object_token: str = ""
    anomaly: str = ""
    niyam_id: str = ""
    resolution: str = ""
    heart_beat: int = 0  # 1-based
    heart_type: str = ""
    skeleton: str = ""  # the title skeleton, S1/S2/S3
    location: str = ""
    place_id: str = ""

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=1, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> "Story":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, raw: dict) -> "Story":
        raw = dict(raw)
        raw["beats"] = [Beat(**b) for b in raw["beats"]]
        return cls(**raw)

    @property
    def narration(self) -> str:
        return " ".join(b.text for b in self.beats)

    @property
    def opening(self) -> str:
        from .hindi import opening

        return opening(self.beats[0].text if self.beats else "")
