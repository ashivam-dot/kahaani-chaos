"""Hindi text the gates can compare: spellings that differ only by a nukta or a chandrabindu, words without
punctuation, Latin-script words and emoji."""
from __future__ import annotations

import re
import unicodedata

NUKTA, CHANDRABINDU, ANUSVARA = "\u093c", "\u0901", "\u0902"
PUNCT = "।॥,.?!:;\"'()‘’“”-–—…"
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF\u2600-\u27BF\u2B00-\u2BFF]")


def norm(text: str) -> str:
    """For comparing spellings: NFC, no nukta, chandrabindu as anusvara, no joiners, Latin in lower case."""
    text = unicodedata.normalize("NFD", text or "").replace(NUKTA, "")
    text = unicodedata.normalize("NFC", text).replace(CHANDRABINDU, ANUSVARA)
    text = re.sub("[\u200c\u200d]", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def words(text: str) -> list[str]:
    """Normalised words with punctuation and emoji stripped (an emoji is not a word: a title of emoji alone has no
    tokens to compare)."""
    bare = EMOJI.sub(" ", norm(text)).replace("\ufe0f", "")
    return [w for w in (t.strip(PUNCT + "|#") for t in bare.split()) if w]


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
