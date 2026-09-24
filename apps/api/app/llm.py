from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol, TypeVar

from pydantic import BaseModel

from .config import get_settings


T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class LLMResult:
    parsed: BaseModel
    request_id: str | None
    input_tokens: int | None
    output_tokens: int | None


class LLMClient(Protocol):
    def parse(
        self, *, prompt: str, evidence: str, schema: type[T], effort: str | None = None
    ) -> LLMResult: ...


class OpenAIClient:
    def __init__(self) -> None:
        from openai import OpenAI

        settings = get_settings()
        if settings.openai_api_key is None:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        self._model = settings.openai_model
        self._client = OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
            max_retries=0,
        )

    def parse(
        self, *, prompt: str, evidence: str, schema: type[T], effort: str | None = None
    ) -> LLMResult:
        """Parse one response. `effort` trades reasoning tokens for latency."""
        from .prompts import SYSTEM_POLICY

        extra = {"reasoning": {"effort": effort}} if effort else {}
        response = self._client.responses.parse(
            model=self._model,
            instructions=f"{SYSTEM_POLICY}\n\n{prompt}",
            input=evidence,
            text_format=schema,
            store=False,
            **extra,
        )
        if response.output_parsed is None:
            raise ValueError("model_returned_no_structured_output")
        usage = response.usage
        return LLMResult(
            parsed=response.output_parsed,
            request_id=response.id,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
        )


@lru_cache
def get_llm_client() -> LLMClient:
    return OpenAIClient()
