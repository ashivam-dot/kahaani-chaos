"""Everything that names the channel, its formats, and when each publishes. The upload step refuses to run while
CHANNEL_ID is not a real YouTube channel id, and refuses any token that signs in to another channel."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import timedelta, timezone

NAME = "सन्नाटपुर की रातें"
NAME_EN = "Sannatpur Ki Raatein"
DISPLAY_NAME = f"{NAME} | {NAME_EN}"
HANDLE = "@KahaaniChaos"  # until the owner claims @SannatpurKiRaatein in Studio; nothing depends on it
# Spellings of the channel's old name that must never be spoken in a story.
NAME_SPOKEN = ("कहानी केऑस", "कहानी कैओस", "कहानी केओस", "कहानी चाओस", "कहानी कैऑस", "kahaani chaos")
TAGLINE = "1996 का एक काल्पनिक गाँव, और उसकी अजीब रातें"
CHANNEL_ID: str = os.environ.get("KC_CHANNEL_ID") or "TBD"
EXPECTED_CHANNEL_ID = "UCX-96TVtOBCEkDMloHuYAHw"
REPO = os.environ.get("GITHUB_REPOSITORY") or "ashivam-dot/kahaani-chaos"
SITE = f"https://github.com/{REPO}"
CONTACT = "aksh.shivam16@gmail.com"

# Every upload carries MARKER + story id as a tag, so a story is never uploaded twice. Never change it after the
# first public upload (it predates the Sannatpur rename on purpose).
MARKER = "kahaani-chaos:"
CATEGORY = "24"  # Entertainment
LANGUAGE = "hi"
# New uploads do not ping subscribers for the first 30 days after the relaunch: most of them came for the old
# twist Shorts. Turn on once more than half the subscribers joined after launch (PLAN.md §6.9).
NOTIFY_SUBSCRIBERS = False

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class Format:
    """One series on the channel: its slots (IST, on the given weekdays, 0 = Monday), how many finished videos the
    ready buffer holds, and the playlist it is filed in when its id variable is set."""
    key: str
    series_hi: str
    slots: tuple[tuple[int, int], ...]
    days: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
    buffer: int = 2
    category: str = CATEGORY
    playlist_env: str = ""
    playlist_title: str = ""

    @property
    def playlist_id(self) -> str:
        return os.environ.get(self.playlist_env, "") if self.playlist_env else ""


# F1 (micro) and M (moment, wordless). F2 (sawaal, choose-one) and F3 (raat, weekly long-form) register here when
# they are built, with their own slots and buffers; nothing below assumes a single format.
FORMATS = {
    "micro": Format(key="micro", series_hi="सन्नाटपुर की छोटी एंट्री", slots=((19, 0),), buffer=2,
                    playlist_env="KC_PLAYLIST_MICRO", playlist_title="सन्नाटपुर की छोटी एंट्री (Shorts)"),
    "moment": Format(key="moment", series_hi="सन्नाटपुर, 1996", slots=((21, 30),), days=(1, 3, 5), buffer=2,
                     playlist_env="KC_PLAYLIST_MOMENT", playlist_title="सन्नाटपुर, 1996 (एक चीज़ ग़लत है)"),
}
FORMAT = os.environ.get("KC_FORMAT") or "micro"  # the format this run produces (the workflow's `format` input)
if FORMAT not in FORMATS:
    raise ValueError(f"KC_FORMAT={FORMAT!r} is not a format; use one of {sorted(FORMATS)}")

SLOTS = FORMATS[FORMAT].slots  # IST: F1 19:00 IST = 13:30 UTC daily; M 21:30 IST on Tue, Thu, Sat
BUFFER_TARGET = FORMATS[FORMAT].buffer

CHANNEL_ID_FORMAT = re.compile(r"^UC[0-9A-Za-z_-]{22}$")


def channel_id_ready() -> bool:
    return bool(CHANNEL_ID_FORMAT.match(CHANNEL_ID))
