# modules/communication/language_router.py

from langdetect import detect, LangDetectException

# Mapping from langdetect codes to framework language codes
LANGUAGE_MAP = {
    "en": "en",
    "vi": "vi",
    "fr": "fr",
    "zh-cn": "zh",
    "zh-tw": "zh",
}

LANGUAGE_NAMES = {
    "en": "English",
    "vi": "Vietnamese",
    "fr": "French",
    "zh": "Chinese",
}


def detect_language(text: str) -> str:
    """
    Detect the primary language of the input text.
    Returns a normalized language code (e.g. 'en', 'vi').
    Falls back to 'en' if detection fails or language is unsupported.
    """
    try:
        raw_code = detect(text)
        return LANGUAGE_MAP.get(raw_code, "en")
    except LangDetectException:
        return "en"


def resolve_language(
    user_specified: str | None,
    input_text: str,
    supported_languages: list[str],
) -> str:
    """
    Resolve the output language for a task.

    Priority order:
    1. User-specified language (if valid and supported by template)
    2. Detected language of input text (if supported by template)
    3. English as fallback

    Returns the resolved language code and emits a warning if fallback
    was applied.
    """
    if user_specified and user_specified in supported_languages:
        return user_specified

    detected = detect_language(input_text)
    if detected in supported_languages:
        return detected

    # Fallback
    return "en"


def get_language_name(code: str) -> str:
    """Return a human-readable language name for display in the UI."""
    return LANGUAGE_NAMES.get(code, code.upper())