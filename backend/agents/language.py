"""
Lightweight language detection for the agent pipeline.

This is a heuristic, not a model: Devanagari script or common
romanised Hindi/Hinglish function words mean "hi", otherwise "en".
It only runs when the caller asked for "auto" — an explicit
language choice from the UI is never overridden.
"""

from __future__ import annotations

# Romanised Hindi function words that show up even in otherwise-English
# sentences ("Hinglish") — enough of these appearing means treat the
# reply language as Hindi/Hinglish rather than pure English.
_HINGLISH_MARKERS = {
    "hai", "kitna", "kitni", "kab", "mera", "meri", "mere", "kya",
    "batao", "chahiye", "karu", "karun", "karna", "baki", "abhi",
    "aap", "aapka", "aapki", "namaste", "dhanyavaad", "shukriya",
    "bhi", "nahi", "haan", "toh", "wala", "kaise", "kyu", "kyun",
}


def detect_language(text: str) -> str:
    """Return "hi" for Hindi/Hinglish input, "en" otherwise."""
    if not text:
        return "en"

    if any("ऀ" <= ch <= "ॿ" for ch in text):
        return "hi"

    words = set(text.lower().replace("?", " ").replace(",", " ").split())
    if words & _HINGLISH_MARKERS:
        return "hi"

    return "en"


def resolve_response_language(requested_language: str, text: str) -> str:
    """Resolve the language to respond in: an explicit choice wins, "auto" gets detected."""
    if requested_language and requested_language != "auto":
        return requested_language
    return detect_language(text)
