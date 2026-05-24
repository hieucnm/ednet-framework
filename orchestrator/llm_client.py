# orchestrator/llm_client.py

import os
from anthropic import Anthropic
from openai import OpenAI
from dataclasses import dataclass

@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int

class LLMClient:
    """
    Provider-agnostic LLM client.
    Switch providers by changing LLM_PRIMARY_PROVIDER in .env.
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PRIMARY_PROVIDER", "anthropic")
        self._anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self._openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        if self.provider == "anthropic":
            return self._call_anthropic(
                system_prompt, user_prompt,
                model or "claude-sonnet-4-6", temperature, max_tokens
            )
        elif self.provider == "openai":
            return self._call_openai(
                system_prompt, user_prompt,
                model or "gpt-4o", temperature, max_tokens
            )
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    def _call_anthropic(self, system_prompt, user_prompt,
                        model, temperature, max_tokens) -> LLMResponse:
        response = self._anthropic.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return LLMResponse(
            text=response.content[0].text,
            model=model,
            provider="anthropic",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def _call_openai(self, system_prompt, user_prompt,
                     model, temperature, max_tokens) -> LLMResponse:
        response = self._openai.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return LLMResponse(
            text=response.choices[0].message.content,
            model=model,
            provider="openai",
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )