# modules/communication/prompt_engine.py

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from jinja2 import Environment, StrictUndefined, TemplateError


TEMPLATES_DIR = Path(__file__).parent / "templates"
SUPPORTED_CONSEQUENCE_LEVELS = {"low", "medium", "high"}


@dataclass
class PromptTemplate:
    template_id: str
    task_type: str
    consequence_level: str
    supported_languages: list[str]
    min_output_words: int
    max_output_words: int
    _system_prompt_raw: str = field(repr=False)
    _user_prompt_raw: str = field(repr=False)

    def render_system(self, variables: dict) -> str:
        """Render the system prompt with provided variables."""
        return self._render(self._system_prompt_raw, variables)

    def render_user(self, variables: dict) -> str:
        """Render the user prompt with provided variables."""
        return self._render(self._user_prompt_raw, variables)

    def _render(self, template_str: str, variables: dict) -> str:
        env = Environment(undefined=StrictUndefined)
        try:
            return env.from_string(template_str).render(**variables)
        except TemplateError as e:
            raise ValueError(
                f"Template rendering failed for '{self.template_id}': {e}. "
                f"Provided variables: {list(variables.keys())}"
            )

    def validate_language(self, language: str) -> None:
        if language not in self.supported_languages:
            raise ValueError(
                f"Language '{language}' is not supported by template "
                f"'{self.template_id}'. "
                f"Supported: {self.supported_languages}"
            )


class PromptEngine:
    """
    Loads and manages prompt templates from the templates directory.
    Templates are cached after first load to avoid repeated disk reads.
    """

    def __init__(self, templates_dir: Path = TEMPLATES_DIR):
        self.templates_dir = templates_dir
        self._cache: dict[str, PromptTemplate] = {}

    def load(self, template_id: str) -> PromptTemplate:
        """Load a template by ID, using cache if available."""
        if template_id in self._cache:
            return self._cache[template_id]

        path = self.templates_dir / f"{template_id}.yaml"
        if not path.exists():
            available = [f.stem for f in self.templates_dir.glob("*.yaml")]
            raise FileNotFoundError(
                f"Template '{template_id}' not found. "
                f"Available templates: {available}"
            )

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        self._validate_schema(raw, template_id)

        template = PromptTemplate(
            template_id=raw["template_id"],
            task_type=raw["task_type"],
            consequence_level=raw["consequence_level"],
            supported_languages=raw["supported_languages"],
            min_output_words=raw.get("min_output_words", 0),
            max_output_words=raw.get("max_output_words", 9999),
            _system_prompt_raw=raw["system_prompt"],
            _user_prompt_raw=raw["user_prompt_template"],
        )

        self._cache[template_id] = template
        return template

    def list_available(self) -> list[dict]:
        """Return metadata for all available templates."""
        result = []
        for path in sorted(self.templates_dir.glob("*.yaml")):
            try:
                template = self.load(path.stem)
                result.append({
                    "template_id": template.template_id,
                    "task_type": template.task_type,
                    "consequence_level": template.consequence_level,
                    "supported_languages": template.supported_languages,
                })
            except Exception:
                continue
        return result

    def _validate_schema(self, raw: dict, template_id: str) -> None:
        required_fields = [
            "template_id", "task_type", "consequence_level",
            "supported_languages", "system_prompt", "user_prompt_template",
        ]
        missing = [f for f in required_fields if f not in raw]
        if missing:
            raise ValueError(
                f"Template '{template_id}' is missing required fields: {missing}"
            )

        if raw["consequence_level"] not in SUPPORTED_CONSEQUENCE_LEVELS:
            raise ValueError(
                f"Template '{template_id}' has invalid consequence_level "
                f"'{raw['consequence_level']}'. "
                f"Must be one of: {SUPPORTED_CONSEQUENCE_LEVELS}"
            )