"""Small text helpers: normalising, comparing, counting questions, and guessing language.

Everything here is deliberately rule-based and explainable. It works on transcripts
(STT output), not on audio.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
WORD = re.compile(r"[\wऀ-ॿ']+", re.UNICODE)

# Common Hindi words as they appear in romanised (Hinglish) transcripts.
ROMAN_HINDI = {
    "aap", "aapka", "aapki", "aapke", "aapko", "hai", "hain", "ho", "hoga", "hogi", "tha", "thi", "kya",
    "kitna", "kitni", "kitne", "kab", "kahan", "kaise", "kaun", "kyun", "nahi", "nahin", "haan", "ji",
    "theek", "thik", "accha", "achha", "bataiye", "batayein", "batao", "chahiye", "karte", "karti",
    "karna", "karenge", "sakte", "sakti", "mein", "me", "se", "ka", "ki", "ke", "ko", "par", "aur",
    "bhi", "toh", "to", "abhi", "pehle", "baad", "kal", "aaj", "rehte", "rehti", "kaam", "naukri",
    "dhanyavaad", "shukriya", "namaste", "hum", "humara", "humari", "main", "mera", "meri", "apna",
    "apni", "raha", "rahi", "rahe", "liye", "wala", "wali", "sahi", "bilkul", "zaroor", "ek", "do",
    "kuch", "sab", "phir", "fir", "dobara", "bol", "bola", "kaha", "samajh", "samjha", "aayega",
    "milega", "milegi", "mahina", "mahine", "din", "ghar", "paas", "dur", "gaadi", "chalate",
}

REPEAT_REQUEST = [
    "repeat", "say that again", "pardon", "sorry?", "phir se", "fir se", "dobara", "kya bola",
    "kya kaha", "samajh nahi", "samjha nahi", "samajh nahin", "फिर से", "दोबारा", "क्या कहा", "समझ नहीं",
]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"[।॥]", " ", text)  # Devanagari danda / double danda
    text = re.sub(r"[^\wऀ-ॿ\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> list[str]:
    return WORD.findall(normalize(text))


def similarity(a: str, b: str) -> float:
    """Highest of character-sequence ratio and token Jaccard, on normalised text."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    jac = len(ta & tb) / len(ta | tb)
    return max(seq, jac)


def containment(short: str, long: str) -> float:
    """Share of the shorter text's tokens that also appear in the longer one."""
    ts, tl = set(tokens(short)), set(tokens(long))
    return len(ts & tl) / len(ts) if ts else 0.0


def contains_phrase(text: str, phrase: str) -> bool:
    return f" {normalize(phrase)} " in f" {normalize(text)} "


def count_questions(text: str) -> int:
    """Questions = question marks (Latin or full-width). STT without punctuation gives 0."""
    return text.count("?") + text.count("？")


def asks_for_repeat(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in REPEAT_REQUEST)


def language_profile(text: str, allowed_english: list[str] | None = None) -> dict[str, float]:
    """Count Hindi tokens (Devanagari or romanised) and English tokens in one turn.

    Allowed English phrases (e.g. "notice period") are removed first, because a Hindi
    persona is still expected to say those in English.
    """
    low = normalize(text)
    for phrase in allowed_english or []:
        low = f" {low} ".replace(f" {normalize(phrase)} ", " ").strip()
    toks = [t for t in low.split() if not t.isdigit()]
    hindi = sum(1 for t in toks if DEVANAGARI.search(t) or t in ROMAN_HINDI)
    english = len(toks) - hindi
    total = len(toks)
    return {"total": total, "hindi": hindi, "english": english,
            "english_share": english / total if total else 0.0,
            "hindi_share": hindi / total if total else 0.0}
