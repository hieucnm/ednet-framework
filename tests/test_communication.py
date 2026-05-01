# tests/test_communication.py

import pytest
from modules.communication.prompt_engine import PromptEngine
from modules.communication.language_router import detect_language, resolve_language


@pytest.fixture
def engine():
    return PromptEngine()


def test_load_all_templates(engine):
    """All five templates must load without errors."""
    template_ids = [
        "meeting_minutes_v1",
        "document_summarizer_v1",
        "curriculum_designer_v1",
        "lecture_generator_v1",
        "collaboration_framework_v1",
    ]
    for tid in template_ids:
        t = engine.load(tid)
        assert t.template_id == tid
        assert t.consequence_level in {"low", "medium", "high"}


def test_render_meeting_minutes(engine):
    """Meeting minutes template renders correctly with valid variables."""
    t = engine.load("meeting_minutes_v1")
    variables = {
        "language": "en",
        "network_name": "AUN/SEED-Net",
        "meeting_date": "2024-11-15",
        "input_text": "Dr. Minh opened the meeting. Action: Prof. Sarah to submit report by Dec 20.",
    }
    system = t.render_system(variables)
    user = t.render_user(variables)
    assert "AUN/SEED-Net" in user
    assert "2024-11-15" in user
    assert "en" in system


def test_unsupported_language_raises(engine):
    """Template should raise when language is not in supported list."""
    t = engine.load("meeting_minutes_v1")
    with pytest.raises(ValueError, match="not supported"):
        t.validate_language("ja")


def test_missing_variable_raises(engine):
    """Template rendering should raise clearly when a variable is missing."""
    t = engine.load("meeting_minutes_v1")
    with pytest.raises(ValueError, match="rendering failed"):
        t.render_user({"language": "en"})  # missing network_name, etc.


def test_language_detection_vietnamese():
    code = detect_language("Chào mừng các bạn đến với hội thảo hôm nay.")
    assert code == "vi"


def test_language_detection_english():
    code = detect_language("Welcome to today's network coordination meeting.")
    assert code == "en"


def test_resolve_language_user_specified(engine):
    t = engine.load("meeting_minutes_v1")
    lang = resolve_language("vi", "Hello world", t.supported_languages)
    assert lang == "vi"


def test_resolve_language_fallback_to_english(engine):
    t = engine.load("meeting_minutes_v1")
    # Japanese is not supported → should fall back to English
    lang = resolve_language("ja", "こんにちは", t.supported_languages)
    assert lang == "en"


def test_list_available_templates(engine):
    available = engine.list_available()
    assert len(available) == 5
    task_types = {t["task_type"] for t in available}
    assert "meeting_minutes" in task_types
    assert "curriculum_design" in task_types