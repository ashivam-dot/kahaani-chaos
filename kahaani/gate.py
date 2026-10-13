"""The code gates every story passes before an editor reads it, and again before it is painted or published.

Each problem is phrased so the writer can fix it in a repair. Hindi words are compared normalised (no nukta, no
chandrabindu), so "ख़ून" and "खून" are the same word.
"""
from __future__ import annotations

import re

from . import config, hindi

WORDS = (140, 200)
BEATS = (9, 12)
HOOK_WORDS = 10
TITLE_CHARS = 70
SCENE_WORDS = (12, 80)
LOOK_WORDS = (6, 60)
CAST = (1, 4)
RECENT_OPENINGS = 10
SUBGENRES = ("jadui-inaam", "shraapit-cheez", "bhoot-rahasya", "samay-chakra", "chatur-chaal")
ENDINGS = ("twist-reveal", "dilemma", "loop-back")

# Asks the channel never makes, anywhere a viewer reads or hears; and openers its hook never uses.
BANNED = ("लाइक", "सब्सक्राइब", "सबस्क्राइब", "शेयर", "फॉलो", "बेल आइकन", "चैनल", "वीडियो", "क्या आप जानते",
          "क्या आपको पता", *config.NAME_SPOKEN)
OPENERS = ("नमस्ते", "नमस्कार", "दोस्तों", "स्वागत", "आज हम", "आज की", "आइए", "हेलो", "कल्पना कीजिए")

# The red lines (CHANNEL.md), as whole Hindi words. Common words that are also people's names (गीता, पूजा, आरती,
# देवी as in "सरला देवी") or plain adjectives (काली रात) are left to the editor.
RED_WORDS = {
    "religion": "भगवान भगवती देवता देवताओं ईश्वर परमेश्वर परमात्मा अल्लाह खुदा राम श्रीराम कृष्ण शिव शंकर महादेव "
                "विष्णु ब्रह्मा हनुमान गणेश गणपति दुर्गा लक्ष्मी सरस्वती पार्वती इंद्र यमराज नारद यीशु पैगंबर "
                "अवतार मंदिर मंदिरों मस्जिद गुरुद्वारा गिरजाघर चर्च दरगाह आश्रम मठ साधु संत ऋषि महर्षि मुनि "
                "पीर फकीर पुजारी मौलवी पादरी पंडित रामायण महाभारत भगवद्गीता वेद पुराण उपनिषद कुरान बाइबिल "
                "ग्रंथ मन्नत",
    "caste or community": "जाति जातियों ब्राह्मण दलित शूद्र क्षत्रिय वैश्य ठाकुर अछूत हिंदू हिन्दू मुसलमान "
                          "मुस्लिम सिख ईसाई",
    "gore": "खून लहू लाश लाशें शव कत्ल हत्या हत्यारा हत्यारे चाकू छुरा",
    "sexual content": "नंगा नंगी नग्न चुंबन सेक्स हवस",
    "self-harm": "आत्महत्या खुदकुशी फांसी",
}
RED_PHRASES = {
    "gore": ("सिर कटा", "कटा सिर", "गला काट"),
    "harm to a child": ("बच्चे की मौत", "बच्ची की मौत", "बच्चे को मार", "बच्ची को मार"),
    "self-harm": ("ज़हर खा",),
    "a claim that it really happened": ("सच्ची घटना", "सच्ची कहानी", "असली घटना", "सत्य घटना"),
}
RED_ENGLISH = {
    "religion": r"gods?|goddess\w*|deit(?:y|ies)|divine|temples?|mosques?|church\w*|gurdwaras?|shrines?|priests?"
                r"|saints?|sages?|sadhus?|monks?|rishis?|avatars?|idols?|shiva|vishnu|krishna|rama|hanuman|ganesh\w*"
                r"|durga|lakshmi|brahma|allah|jesus|buddha|scriptures?|ramayana|mahabharata|gita|vedas?|quran|bible",
    "gore": r"blood(?![- ]red)\w*|gore|gory|corpses?|dead bod(?:y|ies)|sever(?:s|ed|ing)?|behead\w*|decapitat\w*"
            r"|wounds?|wounded|stab(?:s|bed|bing)?|mutilat\w*|dismember\w*",
    "sexual content": r"nude|naked|topless|sexy|seductive|lingerie|cleavage|erotic\w*|kiss\w*",
    "self-harm": r"suicid\w*|self-harm|noose|hang(?:s|ing|ed)? (?:him|her|them)sel(?:f|ves)",
}
_RED_EN = {k: re.compile(rf"\b(?:{v})\b", re.I) for k, v in RED_ENGLISH.items()}
_RED_HI = {k: {hindi.norm(w) for w in v.split()} for k, v in RED_WORDS.items()}
_DIGITS = re.compile(r"[0-9\u0966-\u096f]")
_DEVANAGARI = re.compile(r"[\u0900-\u097f]")


def red_lines_hi(text: str) -> list[str]:
    """The red-line topics a Hindi text touches, with the word that touched each."""
    found = [f"{topic} ({w!r})" for topic, bad in _RED_HI.items() for w in hindi.words(text) if w in bad]
    found += [f"{topic} ({p!r})" for topic, phrases in RED_PHRASES.items() for p in phrases
              if hindi.norm(p) in hindi.norm(text)]
    return list(dict.fromkeys(found))


def red_lines_en(text: str) -> list[str]:
    return [f"{topic} ({m.group(0)!r})" for topic, rx in _RED_EN.items() if (m := rx.search(text or ""))]


def banned(text: str) -> list[str]:
    return [b for b in BANNED if hindi.norm(b) in hindi.norm(text)]


def title_problems(title: str) -> list[str]:
    found = []
    marks = hindi.emoji(title)
    bare = hindi.EMOJI.sub("", title).replace("\ufe0f", "").strip()
    if len(title) > TITLE_CHARS:
        found.append(f"title has {len(title)} characters; at most {TITLE_CHARS}")
    if len(marks) != 1:
        found.append(f"title needs exactly one emoji, has {len(marks)}")
    if not bare.endswith(("!", "?")):
        found.append("title must end with '!' or '?' (the one emoji may follow it)")
    if hindi.latin_words(bare) or hindi.devanagari_share(bare) < 0.95:
        found.append("title must be spoken Hindi in Devanagari, with no English words")
    if any(c in title for c in "<>|#"):
        found.append("title may not contain < > | or #")
    return found


def required_ending(history: list[dict]) -> str:
    """The next ending in the rotation: never the previous Short's."""
    last = history[-1].get("ending") if history else None
    return ENDINGS[(ENDINGS.index(last) + 1) % len(ENDINGS)] if last in ENDINGS else ENDINGS[0]


def check(draft: dict, premise: dict, history: list[dict], rotation: bool = True) -> list[str]:
    """Everything the code refuses in a draft story ({title, hook, beats, cast, ...}), in words the writer can fix.
    rotation False skips the rules that compare with earlier Shorts (a replay of a reviewed story)."""
    if not rotation:
        history = []
    found: list[str] = []
    beats = draft.get("beats") or []
    if not BEATS[0] <= len(beats) <= BEATS[1]:
        found.append(f"needs {BEATS[0]}-{BEATS[1]} beats, has {len(beats)}")
    total = sum(len(hindi.words(b.get("text", ""))) for b in beats)
    if not WORDS[0] <= total <= WORDS[1]:
        found.append(f"needs {WORDS[0]}-{WORDS[1]} spoken Hindi words in total, has {total}")
    cast = draft.get("cast") or []
    names = {c.get("name", "").strip().lower() for c in cast}
    if not CAST[0] <= len(cast) <= CAST[1]:
        found.append(f"cast needs {CAST[0]}-{CAST[1]} characters, has {len(cast)}")
    for c in cast:
        look = c.get("look", "")
        if not LOOK_WORDS[0] <= len(look.split()) <= LOOK_WORDS[1] or _DEVANAGARI.search(look):
            found.append(f"cast {c.get('name')!r} needs an English look of {LOOK_WORDS[0]}-{LOOK_WORDS[1]} words")
        found += [f"cast {c.get('name')!r} look touches {r}" for r in red_lines_en(look)]
    for i, beat in enumerate(beats, 1):
        text = beat.get("text", "")
        if not text.strip():
            found.append(f"beat {i} is empty")
            continue
        if hindi.latin_words(text):
            found.append(f"beat {i} has English words ({hindi.latin_words(text)[0]!r}); spoken Hindi in Devanagari only")
        if _DIGITS.search(text):
            found.append(f"beat {i} has digits; write numbers as Hindi words")
        scene = beat.get("scene", "")
        if not SCENE_WORDS[0] <= len(scene.split()) <= SCENE_WORDS[1] or _DEVANAGARI.search(scene):
            found.append(f"beat {i} needs an English scene of {SCENE_WORDS[0]}-{SCENE_WORDS[1]} words")
        found += [f"beat {i} scene touches {r}; paint the moment before or after" for r in red_lines_en(scene)]
        for p in beat.get("people") or []:
            if p.get("name", "").strip().lower() not in names:
                found.append(f"beat {i} shows {p.get('name')!r}, who is not in the cast")
            if not p.get("expression", "").strip():
                found.append(f"beat {i} gives no expression for {p.get('name')!r}")
            found += [f"beat {i} expression touches {r}" for r in red_lines_en(p.get("expression", ""))]
    for where, text in [(f"beat {i}", b.get("text", "")) for i, b in enumerate(beats, 1)] + \
                       [("title", draft.get("title", "")), ("description", draft.get("description", ""))]:
        found += [f"{where} uses {b!r}: no greetings, channel name, 'did you know' or like/subscribe/share asks"
                  for b in banned(text)]
        found += [f"{where} touches a red line: {r}; remove that word, even in an exclamation or idiom"
                  " (say हाय, बाप रे or अरे instead of हे भगवान or या खुदा)" for r in red_lines_hi(text)]
    if beats:
        hook = beats[0].get("text", "")
        if len(hindi.words(hook)) > HOOK_WORDS:
            found.append(f"beat 1 (the hook) has {len(hindi.words(hook))} words; at most {HOOK_WORDS}")
        if any(hindi.norm(o) in hindi.norm(hook) for o in OPENERS):
            found.append("beat 1 opens like a host (a greeting, 'आज हम', 'आइए'); open on the impossible image")
        opening = hindi.opening(hook)
        if opening and opening in {r.get("opening") for r in history[-RECENT_OPENINGS:]}:
            found.append(f"beat 1 opens with {opening!r} like a recent Short; open differently")
        twist = draft.get("twist_beat")
        if not isinstance(twist, int) or not len(beats) // 2 < twist < len(beats):
            found.append(f"twist_beat must be a beat number after the middle and before the last ({twist!r})")
        if draft.get("ending") == "dilemma" and "?" not in beats[-1].get("text", ""):
            found.append("a dilemma ending's last beat asks the viewer a question ending with '?'")
    found += title_problems(draft.get("title", ""))
    want = required_ending(history) if rotation else draft.get("ending")
    if draft.get("ending") not in ENDINGS:
        found.append(f"ending must be one of {', '.join(ENDINGS)}")
    elif draft.get("ending") != want:
        found.append(f"ending must be {want!r} (the previous Short ended {history[-1].get('ending')!r})"
                     if history else f"ending must be {want!r}")
    if draft.get("subgenre") != premise.get("subgenre"):
        found.append(f"subgenre must be {premise.get('subgenre')!r}")
    description = draft.get("description", "")
    if not description.strip() or hindi.devanagari_share(description) < 0.8 or len(description) > 600:
        found.append("description must be 1-3 Hindi sentences (at most 600 characters)")
    return list(dict.fromkeys(found))


PUBLISHABLE_VOICES = ("gemini-narrator", "chatterbox-narrator-clone")


def voice_ok(voice: dict | None) -> str | None:
    """Why a narration may not be published (anything but the channel's narrator), or None."""
    if not voice:
        return "voice: no narration record"
    if voice.get("identity") != "narrator" or voice.get("engine") not in PUBLISHABLE_VOICES:
        return f"voice: {voice.get('engine')!r} is not the channel's narrator"
    return None
