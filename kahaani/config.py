"""Everything that names the channel, and when it publishes. The upload step refuses to run while CHANNEL_ID is not a
real YouTube channel id, and refuses any token that signs in to another channel."""
from __future__ import annotations

import os
import re
from datetime import timedelta, timezone

NAME = "Kahaani Chaos"
HANDLE = "@KahaaniChaos"
# Spellings of the channel's name that must never be spoken in a story.
NAME_SPOKEN = ("कहानी केऑस", "कहानी कैओस", "कहानी केओस", "कहानी चाओस", "कहानी कैऑस", "kahaani chaos")
TAGLINE = "जादुई और रहस्यमयी कहानियाँ"
CHANNEL_ID: str = os.environ.get("KC_CHANNEL_ID") or "TBD"
EXPECTED_CHANNEL_ID = "UCX-96TVtOBCEkDMloHuYAHw"
REPO = os.environ.get("GITHUB_REPOSITORY") or "ashivam-dot/kahaani-chaos"
SITE = f"https://github.com/{REPO}"
CONTACT = "aksh.shivam16@gmail.com"

# Every upload carries MARKER + story id as a tag, so a story is never uploaded twice. Never change it after the
# first public upload.
MARKER = "kahaani-chaos:"
CATEGORY = "24"  # Entertainment
LANGUAGE = "hi"

IST = timezone(timedelta(hours=5, minutes=30))
SLOTS = ((12, 30), (20, 30))  # IST
BUFFER_TARGET = 2

CHANNEL_ID_FORMAT = re.compile(r"^UC[0-9A-Za-z_-]{22}$")


def channel_id_ready() -> bool:
    return bool(CHANNEL_ID_FORMAT.match(CHANNEL_ID))
