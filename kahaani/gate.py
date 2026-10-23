"""The code gates every F1 micro-entry passes before an editor reads it, and again before it is painted or published.

Each problem is phrased so the writer can fix it in a repair. Hindi words are compared normalised (no nukta, no
chandrabindu), so "ख़ून" and "खून" are the same word. Every comparison tokenises with kahaani.hindi, never \\w+ or
[a-z0-9]+, which see nothing in Devanagari. Each floor has its ceiling: a band, never a one-sided threshold.
"""
from __future__ import annotations

import re

from . import bible, config, hindi

# F1 "सन्नाटपुर की छोटी एंट्री" bands (PLAN.md §4 F1): 35-55 s spoken, hard gate 30-58 s at render.
WORDS = (85, 130)
BEATS = (5, 7)
HOOK_WORDS = 10
HOOK_STRIP_WORDS = (3, 5)
TITLE_CHARS = (40, 75)
TITLE_EMOJI = (1, 2)  # PLAN.md §7.2: one or two (📻😨)
TITLE_SUFFIX = " | सन्नाटपुर"
TITLE_OBJECT_WITHIN = 5
SCENE_WORDS = (12, 80)
CAST = (1, 4)
DURATION = (30.0, 58.0)
END_CARD = 2.4  # seconds of end card compose adds after the narration (compose.END_CARD)
PAYOFF_BY = 0.75  # the turn lands within the first three quarters of the runtime
ENDINGS = ("loop-back", "register-line", "open-question", "next-raat-tease")
RESOLUTIONS = ("leave-it-be", "kindness", "bargain", "outsmart")
SKELETONS = ("S1", "S2", "S3")
# 1996, in words (digits are never spoken from the screen): beat 2 opens the memory with the year.
YEAR_WORD = "छियानवे"

# Asks the channel never makes, anywhere a viewer reads or hears; and openers its hook never uses. The bare nouns
# चैनल and वीडियो are everyday 1996 things in a story (the TV's channel, the video parlour), so a beat may say them;
# only the asks are refused there. Metadata never needs them (META_BANNED).
BANNED = ("लाइक", "सब्सक्राइब", "सबस्क्राइब", "शेयर", "फॉलो", "बेल आइकन", "हमारे चैनल", "इस चैनल", "चैनल को", "चैनल पर",
          "इस वीडियो", "वीडियो को", "वीडियो पसंद", "क्या आप जानते", "क्या आपको पता", *config.NAME_SPOKEN)
META_BANNED = ("चैनल", "वीडियो")
OPENERS = ("नमस्ते", "नमस्कार", "दोस्तों", "स्वागत", "आज हम", "आज की", "आइए", "हेलो", "कल्पना कीजिए")
# Names the bible replaced after its name check (bible/README.md): never in a script.
RETIRED_NAMES = ("अंशु", "शबनम", "मोंटी", "ज़रीना")

# The red lines (CHANNEL.md, PLAN.md §7.4 a-b), as whole Hindi words. The bible's own never_exists lists are added
# below, so a word the bible bans is banned here without being copied twice.
RED_WORDS = {
    "religion": "भगवान भगवती देवता देवताओं देवी ईश्वर परमेश्वर परमात्मा अल्लाह खुदा राम श्रीराम कृष्ण शिव शंकर "
                "महादेव विष्णु ब्रह्मा हनुमान गणेश गणपति दुर्गा लक्ष्मी सरस्वती पार्वती इंद्र यमराज नारद यीशु "
                "पैगंबर अवतार मंदिर मंदिरों मस्जिद गुरुद्वारा गिरजाघर चर्च दरगाह मज़ार आश्रम मठ साधु संत ऋषि "
                "महर्षि मुनि पीर फकीर पुजारी मौलवी पादरी पंडित रामायण महाभारत भगवद्गीता वेद पुराण उपनिषद कुरान "
                "बाइबिल ग्रंथ मन्नत",
    "ritual": "पूजा आरती हवन नमाज़ तांत्रिक तंत्र ओझा झाड़फूँक मंत्र ताबीज़ अनुष्ठान टोना टोटका बलि "
              "कब्र क़ब्रिस्तान कब्रिस्तान श्मशान समाधि",
    "a banned being": "ब्रह्मराक्षस पिशाच बेताल वेताल चुड़ैल डायन जिन्न प्रेत भैरव यमदूत",
    "caste or community": "जाति जातियों ब्राह्मण दलित शूद्र क्षत्रिय वैश्य ठाकुर अछूत हिंदू हिन्दू मुसलमान "
                          "मुस्लिम सिख ईसाई",
    "gore": "खून लहू लाश लाशें शव कत्ल हत्या हत्यारा हत्यारे चाकू छुरा",
    "sexual content": "नंगा नंगी नग्न चुंबन सेक्स हवस",
    "self-harm": "आत्महत्या खुदकुशी फांसी",
    "the real world": "दिल्ली मुंबई बंबई कोलकाता कलकत्ता लखनऊ पटना कानपुर इलाहाबाद प्रयागराज वाराणसी बनारस "
                      "आगरा मेरठ भोपाल इंदौर जयपुर बिहार राजस्थान पंजाब हरियाणा गंगा यमुना अमिताभ शाहरुख सचिन "
                      "तेंदुलकर गांधी नेहरू",
}
# The bible's brands (world.yaml never_exists.brands.map) as Hindi spells them: one word, or a phrase where the
# word alone is everyday Hindi (उषा is a name, हीरो a film hero). test_hindi_gates checks every brand has a spelling.
BRANDS_HI = {
    "Doordarshan": ("दूरदर्शन",), "Ambassador": ("एंबेसडर", "ऐंबेसडर"), "Rasna": ("रसना",),
    "Parle": ("पारले", "पार्ले"), "Campa Cola": ("कैंपा", "कैम्पा कोला"), "Nataraj": ("नटराज",),
    "Philips": ("फिलिप्स",), "Murphy": ("मर्फी",), "HMT": ("एचएमटी",), "Atlas": ("एटलस",),
    "Hero": ("हीरो साइकिल", "हीरो की साइकिल", "हीरो जेट"), "BSA": ("बीएसए",), "Bajaj": ("बजाज",),
    "Rajdoot": ("राजदूत",), "Lux": ("लक्स",), "Lifebuoy": ("लाइफबॉय", "लाइफबाय"),
    "Usha": ("उषा मशीन", "उषा की मशीन", "उषा सिलाई"), "Binaca": ("बिनाका",), "Vividh Bharati": ("विविध भारती",),
}
RED_PHRASES = {
    "gore": ("सिर कटा", "कटा सिर", "गला काट"),
    "harm to a child": ("बच्चे की मौत", "बच्ची की मौत", "बच्चे को मार", "बच्ची को मार"),
    "self-harm": ("ज़हर खा",),
    "a claim that it really happened": ("सच्ची घटना", "सच्ची कहानी", "असली घटना", "सत्य घटना"),
    "ritual": ("झाड़ फूँक", "अमावस की पूजा", "अमावस का अनुष्ठान", "जादू टोना"),
    "a banned being": ("भूत प्रेत",),
    "the real world": ("उत्तर प्रदेश", "मध्य प्रदेश", "ताज महल"),
}
RED_ENGLISH = {
    "religion": r"gods?|goddess\w*|deit(?:y|ies)|divine|temples?|mosques?|church\w*|gurdwaras?|shrines?|dargahs?"
                r"|priests?|saints?|sages?|sadhus?|monks?|rishis?|avatars?|idols?|shiva|vishnu|krishna|rama"
                r"|hanuman|ganesh\w*|durga|lakshmi|brahma|allah|jesus|buddha|scriptures?|ramayana|mahabharata|gita"
                r"|vedas?|quran|bible|tilak|rosar(?:y|ies)|prayer flags?|holy|sacred|crescent|crucifix",
    "ritual": r"puja|pooja|aarti|arti|havan|namaz|tantrik\w*|exorcis\w*|ritual\w*|incantation\w*|amulets?"
              r"|talisman\w*|sacrific\w*|graves?|graveyards?|cemeter(?:y|ies)|crematori\w*|cremation|tombs?",
    "a banned being": "|".join(bible.banned_beings_en()) + r"|demons?|witch\w*|possess(?:ed|ion)|curse[ds]?",
    "gore": r"blood(?![- ]red)\w*|gore|gory|corpses?|dead bod(?:y|ies)|sever(?:s|ed|ing)?|behead\w*|decapitat\w*"
            r"|wounds?|wounded|stab(?:s|bed|bing)?|mutilat\w*|dismember\w*",
    "sexual content": r"nude|naked|topless|sexy|seductive|lingerie|cleavage|erotic\w*|kiss\w*",
    "self-harm": r"suicid\w*|self-harm|noose|hang(?:s|ing|ed)? (?:him|her|them)sel(?:f|ves)",
    "the real world": "|".join(re.escape(b.lower()) for b in bible.brands() if b.lower() != "hero")
                      + r"|hero cycles?|logos?|brand names?|delhi|mumbai|bombay|kolkata|calcutta|lucknow|patna"
                        r"|varanasi|benares|agra|jaipur|bihar|uttar pradesh|rajasthan|punjab|ganga|ganges|yamuna"
                        r"|taj mahal|amitabh|shah ?rukh|tendulkar|gandhi|nehru|true story",
}
# Metadata that reads as made for kids (PLAN.md §5): never in a title, description or tag.
MFK_HI = ("बच्चों", "बच्चों के लिए", "बाल कहानी", "बाल कथा", "कार्टून", "लोरी", "नैतिक कहानी", "शिक्षाप्रद",
          "सोने से पहले की कहानी", "परी कथा")
MFK_EN = r"kids?|kiddie|children'?s|cartoons?|bedtime|nursery|moral stor(?:y|ies)|rhymes?|toddlers?|preschool"
TITLE_NEVER = ("चौकीदार", "90s की वो रात", "ghibli")


def forms(word: str) -> set[str]:
    """A normalised Hindi noun with its plural, oblique and vocative endings, so a red word is caught however the
    sentence bends it: मस्जिद -> मस्जिदें मस्जिदों, लाश -> लाशें लाशों, हत्या -> हत्याएं हत्याओं, पुजारी ->
    पुजारियों, साधु -> साधुओं, हिंदू -> हिंदुओं. Exact forms only, never a prefix (राम must not catch रामू)."""
    out, last = {word}, word[-1:]
    if last == "\u093e":  # -ा
        out |= {word + "एं", word + "ओं", word + "ओ", word[:-1] + "\u0947", word[:-1] + "ों", word[:-1] + "ो"}
    elif last == "\u0940":  # -ी
        out |= {word[:-1] + e for e in ("ियां", "ियों", "ियो")}
    elif last == "\u093f":  # -ि
        out |= {word + e for e in ("यां", "यों", "यो")}
    elif last == "ई":
        out |= {word[:-1] + e for e in ("इयां", "इयों", "इयो")}
    elif last in ("\u0941", "\u0942"):  # -ु -ू
        out |= {word[:-1] + "\u0941" + e for e in ("एं", "ओं", "ओ")}
    elif "\u0915" <= last <= "\u0939":  # a consonant
        out |= {word + e for e in ("ें", "ों", "ो")}
    return out


_RED_EN = {k: re.compile(rf"\b(?:{v})\b", re.I) for k, v in RED_ENGLISH.items()}
_RED_HI: dict[str, set[str]] = {k: set() for k in RED_WORDS}
for _topic, _words in RED_WORDS.items():
    for _w in _words.split():
        _RED_HI[_topic] |= forms(hindi.norm(_w))
for _spellings in BRANDS_HI.values():
    for _b in _spellings:
        if len(hindi.words(_b)) > 1:
            RED_PHRASES["the real world"] += (_b,)
        else:
            _RED_HI["the real world"] |= forms(hindi.words(_b)[0])
# बाबा is banned in the holy-man sense only; as grandfather or a fond address it is everyday Hindi (the editor judges).
for _term in (t for t in bible.banned_terms_hi() if t != "बाबा"):
    if len(hindi.words(_term)) > 1:  # "अमावस का कोई अनुष्ठान", "पूजा-घर"
        RED_PHRASES.setdefault("ritual", ())
        RED_PHRASES["ritual"] += (_term,)
    else:
        _RED_HI["religion"] |= forms(hindi.words(_term)[0])
_MFK_EN = re.compile(rf"\b(?:{MFK_EN})\b", re.I)
_DIGITS = re.compile(r"[0-9०-९]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _has_phrase(text: str, phrase: str) -> bool:
    """phrase's words in a row in text, whatever punctuation joins them; the last word may take an ending (ज़हर खा
    catches ज़हर खाया)."""
    return f" {' '.join(hindi.words(phrase))}" in f" {' '.join(hindi.words(text))}"


def red_lines_hi(text: str) -> list[str]:
    """The red-line topics a Hindi text touches, with the word that touched each."""
    found = [f"{topic} ({w!r})" for topic, bad in _RED_HI.items() for w in hindi.words(text) if w in bad]
    found += [f"{topic} ({p!r})" for topic, phrases in RED_PHRASES.items() for p in phrases if _has_phrase(text, p)]
    return list(dict.fromkeys(found))


def _flat(text: str) -> str:
    return "".join(hindi.words(text))


# A hashtag is one run of letters (#बच्चोंकीकहानी, #truestory), so no whole-word gate sees inside it: these are looked
# for as substrings of the flattened tag. Hindi red words shorter than four letters are left to the word gates, or
# राम would refuse #ग्रामीण.
_FLAT_WATCH = tuple(dict.fromkeys(
    [_flat(w) for w in MFK_HI] + ["kids", "kiddie", "children", "cartoon", "bedtime", "nursery", "moralstor", "rhyme",
                                  "toddler", "preschool", "truestory", "realstory"]
    + [_flat(p) for phrases in RED_PHRASES.values() for p in phrases]
    + [_flat(b) for spellings in BRANDS_HI.values() for b in spellings]
    + [hindi.norm(w) for words in RED_WORDS.values() for w in words.split() if len(hindi.norm(w)) >= 4]))


def hashtag_problems(tags: list[str]) -> list[str]:
    """Hashtags that hide a made-for-kids word, a red line or a brand inside one run of letters."""
    found = []
    for tag in tags:
        flat = _flat(tag)
        hit = next((w for w in _FLAT_WATCH if w and w in flat), None)
        if hit:
            found.append(f"hashtag {tag!r} hides {hit!r} (made for kids, a red line or a brand)")
    return found


def scene_ok(scene: str) -> bool:
    return SCENE_WORDS[0] <= len((scene or "").split()) <= SCENE_WORDS[1] and not _DEVANAGARI.search(scene or "")


def red_lines_en(text: str) -> list[str]:
    return [f"{topic} ({m.group(0)!r})" for topic, rx in _RED_EN.items() if (m := rx.search(text or ""))]


def banned(text: str) -> list[str]:
    return [b for b in BANNED if hindi.norm(b) in hindi.norm(text)]


def mfk_metadata(text: str) -> list[str]:
    """Made-for-kids signals in a title, description or tag (Hindi phrases, English words)."""
    found = [w for w in MFK_HI if hindi.norm(w) in hindi.words(text) or (" " in w and hindi.norm(w) in hindi.norm(text))]
    found += [m.group(0) for m in _MFK_EN.finditer(text or "")]
    return list(dict.fromkeys(found))


def _bare(title: str) -> str:
    """The title without its suffix and emoji."""
    text = title.strip()
    if text.endswith(TITLE_SUFFIX.strip()):
        text = text[: -len(TITLE_SUFFIX.strip())].rstrip().rstrip("|").rstrip()
    return hindi.EMOJI.sub("", text).replace("️", "").strip()


S2_AGENT_WITHIN = TITLE_OBJECT_WITHIN  # S2's ने follows the object, which opens the title


def skeleton_of(title: str) -> str:
    """S3 is a question hook, S2 '<object> ने <strange action>', S1 '<act>… <impossible result>'. A ने alone does not
    make S2: 'प्रभात ने साइकिल रोकी… और लाइट जल उठी' is S1 (a person acts, an ellipsis splits act from result)."""
    bare = _bare(title)
    if bare.endswith("?"):
        return "S3"
    have = hindi.words(bare)
    names = {hindi.norm(c["name"]["hi"]) for c in bible.cast().values()}
    at = next((i for i, w in enumerate(have) if w == "ने"), None)
    if at is not None and 1 <= at <= S2_AGENT_WITHIN and "…" not in bare and "..." not in bare \
            and have[at - 1] not in names:
        return "S2"
    return "S1"


# Masculine -आ nouns change their last vowel when the sentence bends them (पंखा -> पंखे पंखों, कुआँ -> कुएँ कुओं).
_STEM_ENDS = ("\u093e\u0902", "\u093e", "आं", "आ")
_BENT = ("\u093e", "\u0947", "\u094b\u0902", "\u0940\u0902", "\u0940", "\u0947\u0902", "\u094b", "ए", "एं", "ओं", "ओ",
         "आ", "आं")


def names_word(word: str, token_word: str) -> bool:
    """word is token_word, or token_word with an ending (साइकिल -> साइकिलें, पंखा -> पंखे, कुआँ -> कुएँ)."""
    if word.startswith(token_word):
        return True
    stem = next((token_word[:-len(e)] for e in _STEM_ENDS if token_word.endswith(e)), None)
    return bool(stem) and len(stem) >= 2 and word[len(stem):] in _BENT and word.startswith(stem)


def object_in_title(title: str, token: str, within: int = TITLE_OBJECT_WITHIN) -> bool:
    """The object token (one or more words; a word may take an ending, साइकिल -> साइकिलें, पंखा -> पंखे) starts within
    the first `within` words of the title."""
    want, have = hindi.words(token), hindi.words(_bare(title))
    if not want or not have:
        return False
    for i in range(min(within, len(have))):
        got = have[i:i + len(want)]
        if len(got) == len(want) and all(names_word(g, w) for g, w in zip(got, want)):
            return True
    return False


def title_problems(title: str, object_token: str | None = None, skeleton: str | None = None) -> list[str]:
    found = []
    marks = hindi.emoji(title)
    bare = _bare(title)
    if not TITLE_CHARS[0] <= len(title) <= TITLE_CHARS[1]:
        found.append(f"title has {len(title)} characters; it needs {TITLE_CHARS[0]}-{TITLE_CHARS[1]}")
    if not TITLE_EMOJI[0] <= len(marks) <= TITLE_EMOJI[1]:
        found.append(f"title needs {TITLE_EMOJI[0]}-{TITLE_EMOJI[1]} emoji, has {len(marks)}")
    if "|" in title and not title.rstrip().endswith(TITLE_SUFFIX):
        found.append(f"a '|' may only appear as the suffix {TITLE_SUFFIX.strip()!r} at the very end")
    if title.count("|") > 1 or any(c in title for c in "<>#"):
        found.append("title may not contain < > # or more than one |")
    if hindi.devanagari_share(bare) < 0.8:
        found.append("title must be spoken Hindi in Devanagari (an object's short Latin name like PCO is fine)")
    if object_token and not object_in_title(title, object_token):
        found.append(f"title must name the object {object_token!r} within its first {TITLE_OBJECT_WITHIN} words")
    if skeleton and skeleton_of(title) != skeleton:
        found.append(f"title must follow skeleton {skeleton} ({SKELETON_HELP[skeleton]}); it reads as "
                     f"{skeleton_of(title)}")
    found += [f"title uses {w!r}, which never goes in a title" for w in TITLE_NEVER
              if hindi.norm(w) in hindi.norm(title)]
    found += [f"title reads as made for kids ({w!r})" for w in mfk_metadata(title)]
    return found


SKELETON_HELP = {"S1": "'<the 90s act>… और <the impossible result>! <emoji>'",
                 "S2": "'<object> ने <strange action> <emoji> | सन्नाटपुर'",
                 "S3": "a question hook: '<object> … क्यों/कैसे/किसने …? <emoji>'"}


def ending_problems(beats: list[dict], ending: str, object_token: str) -> list[str]:
    """What each ending type needs from the last beat (PLAN.md §4 F1 endings)."""
    last = beats[-1].get("text", "") if beats else ""
    words = hindi.words(last)
    if ending == "loop-back" and not any(names_word(w, t) for t in hindi.words(object_token) for w in words):
        return [f"a loop-back ending's last beat echoes frame 0: name the {object_token!r} again"]
    if ending == "register-line" and not any(w.startswith(hindi.norm("रजिस्टर")) for w in words):
        return ["a register-line ending's last beat has झब्बू write one line in his रजिस्टर"]
    if ending == "open-question" and not last.rstrip().endswith("?"):
        return ["an open-question ending's last beat asks the viewer one question, ending with '?'"]
    if ending == "next-raat-tease" and hindi.norm("शनिवार") not in words:
        return ["a next-raat-tease ending's last beat says the full night comes on शनिवार"]
    return []


def check(draft: dict, premise: dict, history: list[dict], rotation: bool = True) -> list[str]:
    """Everything the code refuses in a draft micro-entry, in words the writer can fix. premise is the bank entry
    (premises.premise_for). rotation False skips the rules that compare with earlier Shorts (a replay of a reviewed
    story)."""
    from . import variation

    found: list[str] = []
    beats = draft.get("beats") or []
    if not BEATS[0] <= len(beats) <= BEATS[1]:
        found.append(f"needs {BEATS[0]}-{BEATS[1]} beats, has {len(beats)}")
    total = sum(len(hindi.words(b.get("text", ""))) for b in beats)
    if not WORDS[0] <= total <= WORDS[1]:
        # Rewrites asked only for the band land on its edge (134 after two repairs in dry run 39878445511), so name
        # the cut or the addition and aim for the middle.
        aim = sum(WORDS) // 2
        change = f"cut about {total - aim} words" if total > WORDS[1] else f"add about {aim - total} words"
        found.append(f"needs {WORDS[0]}-{WORDS[1]} spoken Hindi words in total, has {total}: {change} so it lands "
                     f"near {aim}")
    cast = draft.get("cast") or []
    ids = {c.get("id") for c in cast}
    if not CAST[0] <= len(cast) <= CAST[1]:
        found.append(f"cast needs {CAST[0]}-{CAST[1]} characters, has {len(cast)}")
    found += [f"cast {c.get('id')!r} is not a bible character ({', '.join(bible.ON_SCREEN)})" for c in cast
              if c.get("id") not in bible.ON_SCREEN]
    for i, beat in enumerate(beats, 1):
        text = beat.get("text", "")
        if not text.strip():
            found.append(f"beat {i} is empty")
            continue
        if hindi.latin_words(text):
            found.append(f"beat {i} has English words ({hindi.latin_words(text)[0]!r}); spoken Hindi in Devanagari only")
        if _DIGITS.search(text):
            found.append(f"beat {i} has digits; write numbers as Hindi words")
        found += [f"beat {i} uses the retired name {n!r}; the cast is झब्बू, प्रभात, नुज़हत and शैलेश"
                  for n in RETIRED_NAMES if hindi.norm(n) in hindi.words(text)]
        scene = beat.get("scene", "")
        if not scene_ok(scene):
            found.append(f"beat {i} needs an English scene of {SCENE_WORDS[0]}-{SCENE_WORDS[1]} words")
        found += [f"beat {i} scene touches {r}; paint something else" for r in red_lines_en(scene)]
        for p in beat.get("people") or []:
            if p.get("name", "").strip() not in ids:
                found.append(f"beat {i} shows {p.get('name')!r}, who is not in the cast ids")
            if not p.get("expression", "").strip():
                found.append(f"beat {i} gives no expression for {p.get('name')!r}")
            found += [f"beat {i} expression touches {r}" for r in red_lines_en(p.get("expression", ""))]
    meta = [("title", draft.get("title", "")), ("description", draft.get("description", "")),
            ("hook strip", draft.get("hook_strip", "")), ("hashtags", " ".join(draft.get("hashtags") or []))]
    for where, text in [(f"beat {i}", b.get("text", "")) for i, b in enumerate(beats, 1)] + meta:
        found += [f"{where} uses {b!r}: no greetings, channel name, 'did you know' or like/subscribe/share asks"
                  for b in banned(text)]
        found += [f"{where} touches a red line: {r}; remove that word, even in an exclamation or idiom"
                  " (say हाय, बाप रे or अरे instead of हे भगवान or या खुदा)" for r in red_lines_hi(text)]
    for where, text in meta:
        found += [f"{where} uses {b!r}: metadata never talks about the channel or the video" for b in META_BANNED
                  if hindi.norm(b) in hindi.words(text)]
        found += [f"{where} touches a red line: {r}" for r in red_lines_en(text)]
    for where, text in meta[1:2] + meta[3:]:
        found += [f"{where} reads as made for kids ({w!r}); this channel is for adults" for w in mfk_metadata(text)]
    found += hashtag_problems(draft.get("hashtags") or [])
    token = premise.get("object_token") or draft.get("object_token") or ""
    if draft.get("object_token") and premise.get("object_token") and \
            hindi.norm(draft["object_token"]) != hindi.norm(premise["object_token"]):
        found.append(f"object_token must be {premise['object_token']!r}")
    if beats:
        hook = beats[0].get("text", "")
        if len(hindi.words(hook)) > HOOK_WORDS:
            found.append(f"beat 1 (the hook) has {len(hindi.words(hook))} words; at most {HOOK_WORDS}")
        if token and not any(names_word(w, t) for t in hindi.words(token)[:1] for w in hindi.words(hook)[:HOOK_WORDS]):
            found.append(f"beat 1 (the hook) must name the object {token!r} and its anomaly in its first "
                         f"{HOOK_WORDS} words")
        if any(hindi.norm(o) in hindi.norm(hook) for o in OPENERS):
            found.append("beat 1 opens like a host (a greeting, 'आज हम', 'आइए'); open on the impossible image")
        if len(beats) > 1 and hindi.norm(YEAR_WORD) not in hindi.words(beats[1].get("text", "")):
            found.append("beat 2 opens the memory with the year in words: 'उन्नीस सौ छियानवे, उस रात…'")
        turn, heart = draft.get("twist_beat"), draft.get("heart_beat")
        if not isinstance(turn, int) or not 3 <= turn < len(beats):
            found.append(f"turn_beat (the trio realises the rule) must be a beat from 3 to {len(beats) - 1} ({turn!r})")
        if not isinstance(heart, int) or not (isinstance(turn, int) and turn <= heart < len(beats)):
            found.append(f"heart_beat must come at or after the turn and before the last beat ({heart!r})")
        found += ending_problems(beats, draft.get("ending", ""), token)
    strip = draft.get("hook_strip", "")
    n = len(hindi.words(strip))
    if not HOOK_STRIP_WORDS[0] <= n <= HOOK_STRIP_WORDS[1] or hindi.devanagari_share(strip) < 0.95 or \
            hindi.emoji(strip) or _DIGITS.search(strip):
        found.append(f"hook_strip must be {HOOK_STRIP_WORDS[0]}-{HOOK_STRIP_WORDS[1]} Hindi words in Devanagari, "
                     f"no emoji or digits (has {n})")
    found += title_problems(draft.get("title", ""), token or None, premise.get("title_skeleton"))
    want = premise.get("ending_type")
    if draft.get("ending") not in ENDINGS:
        found.append(f"ending_type must be one of {', '.join(ENDINGS)}")
    elif want and draft.get("ending") != want:
        found.append(f"ending_type must be {want!r}")
    if premise.get("resolution_type") and draft.get("resolution") != premise["resolution_type"]:
        found.append(f"resolution_type must be {premise['resolution_type']!r}")
    rule = draft.get("niyam_id")
    if rule not in bible.niyam():
        found.append(f"niyam_id {rule!r} is not a rule in canon.json")
    elif premise.get("niyam_id") and rule != premise["niyam_id"]:
        found.append(f"niyam_id must be {premise['niyam_id']!r}, this entry's rule")
    description = draft.get("description", "")
    if not description.strip() or hindi.devanagari_share(description) < 0.8 or len(description) > 600:
        found.append("description must be 1-3 Hindi sentences (at most 600 characters)")
    if rotation:
        found += variation.problems(variation.row(draft, premise), history)
    return list(dict.fromkeys(found))


def runtime_problems(seconds: float | None) -> list[str]:
    """Gate (k) on the finished Short (narration and end card): inside DURATION, and measured at all."""
    if seconds is None:
        return ["the finished Short's length could not be measured"]
    if not DURATION[0] <= seconds <= DURATION[1]:
        return [f"the finished Short runs {seconds:.1f} s; F1 needs {DURATION[0]:.0f}-{DURATION[1]:.0f} s"]
    return []


def timing_problems(story, timing: dict) -> list[str]:
    """Gate (g)/(k) on the narration as spoken: the Short it makes (narration and END_CARD) inside the runtime band,
    and the turn landing by PAYOFF_BY of the narration."""
    found = []
    spoken = float(timing.get("duration") or 0)
    if not DURATION[0] <= spoken + END_CARD <= DURATION[1]:
        found.append(f"narration runs {spoken:.1f} s, a {spoken + END_CARD:.1f} s Short with its end card; F1 needs "
                     f"{DURATION[0]:.0f}-{DURATION[1]:.0f} s")
    spans = timing.get("beats") or []
    turn = getattr(story, "twist_beat", 0)
    if spoken and 1 <= turn <= len(spans):
        start = float(spans[turn - 1][0])
        if start > PAYOFF_BY * spoken:
            found.append(f"the turn starts at {start:.1f} s, after {PAYOFF_BY:.0%} of the {spoken:.1f} s narration")
    return found


PUBLISHABLE_VOICES = ("gemini-narrator", "chatterbox-narrator-clone")


def voice_ok(voice: dict | None) -> str | None:
    """Why a narration may not be published (anything but the channel's narrator), or None."""
    if not voice:
        return "voice: no narration record"
    if voice.get("identity") != "narrator" or voice.get("engine") not in PUBLISHABLE_VOICES:
        return f"voice: {voice.get('engine')!r} is not the channel's narrator"
    return None
