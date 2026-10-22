"""Hindi text the gates can compare: spellings that differ only by a nukta, a chandrabindu or a nasal written as a
half letter (मन्दिर / मंदिर), words without punctuation (inside a word too: भूत-प्रेत is two words, बिजली गई…और is
three), Latin-script words and emoji (one emoji per picture, however many code points it takes)."""
from __future__ import annotations

import re
import unicodedata

NUKTA, CHANDRABINDU, ANUSVARA, VIRAMA = "\u093c", "\u0901", "\u0902", "\u094d"
PUNCT = "।॥,.?!:;\"'()‘’“”-–—…|#/"
# A nasal half letter before a consonant of its own class is the anusvara written another way: ङ्क ञ्च ण्ड न्द म्ब.
_NASAL = re.compile("ङ\u094d(?=[क-घ])|ञ\u094d(?=[च-झ])|ण\u094d(?=[ट-ढ])|न\u094d(?=[त-ध])|म\u094d(?=[प-भ])")
_PICTO = "\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF\u2300-\u23ff\u2600-\u27bf\u2b00-\u2bff"
_MODS = "\ufe0f\U0001F3FB-\U0001F3FF"
# One emoji as a viewer sees it: a flag (two regional letters), a keycap (3️⃣), or a picture with its skin tone,
# variation selector and any zero-width-joined pictures (😶‍🌫️ is one).
EMOJI = re.compile(f"[\U0001F1E6-\U0001F1FF]{{2}}|[0-9#*]\ufe0f?\u20e3|[{_PICTO}][{_MODS}]*(?:\u200d[{_PICTO}][{_MODS}]*)*")
_BREAK = re.compile("[" + re.escape(PUNCT) + "]")


def norm(text: str) -> str:
    """For comparing spellings: NFC, no nukta, chandrabindu and homorganic nasal half letters as anusvara, no
    joiners, Latin in lower case."""
    text = unicodedata.normalize("NFD", text or "").replace(NUKTA, "")
    text = unicodedata.normalize("NFC", text).replace(CHANDRABINDU, ANUSVARA)
    text = _NASAL.sub(ANUSVARA, re.sub("[\u200c\u200d]", "", text))
    return re.sub(r"\s+", " ", text).strip().lower()


def words(text: str) -> list[str]:
    """Normalised words, split at any punctuation as well as at spaces, with emoji dropped (an emoji is not a word:
    a title of emoji alone has no tokens to compare)."""
    bare = EMOJI.sub(" ", text or "").replace("\ufe0f", "").replace("\u20e3", "")
    return norm(_BREAK.sub(" ", norm(bare))).split()


def opening(text: str, n: int = 2) -> str:
    """A line's first n words, normalised: two Shorts may not open the same way."""
    return " ".join(words(text)[:n])


def devanagari_share(text: str) -> float:
    letters = [ch for ch in text if unicodedata.category(ch)[0] in "LM"]
    return sum("\u0900" <= ch <= "\u097f" for ch in letters) / max(len(letters), 1)


def latin_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9'’\-]*", text or "")


def emoji(text: str) -> list[str]:
    return EMOJI.findall(text or "")
