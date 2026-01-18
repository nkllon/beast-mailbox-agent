"""OpenAI provider adapter."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)

from .base import BaseProvider, ProviderError, ProviderResponse, PromptRequest


def _build_messages(prompt: str, context: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    if context:
        context_messages = context.get("messages")
        if isinstance(context_messages, list):
            for item in context_messages:
                if isinstance(item, dict) and "role" in item and "content" in item:
                    messages.append({"role": str(item["role"]), "content": str(item["content"])})
    messages.append({"role": "user", "content": prompt})
    return messages


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError))


class OpenAIChatProvider(BaseProvider):
    """Adapter for OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: str,
        default_model: str,
        *,
        timeout: float,
        default_options: Optional[Dict[str, Any]] = None,
    ):
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout)
        self._default_model = default_model
        self._default_options = default_options or {}

    async def generate(self, request: PromptRequest) -> ProviderResponse:
        options = dict(self._default_options)
        options.update(request.options or {})
        model = options.pop("model", self._default_model)

        client = self._client
        timeout = options.pop("timeout", None)
        if timeout is not None:
            client = client.with_options(timeout=timeout)

        try:
            response = await client.chat.completions.create(
                model=model,
                messages=_build_messages(request.prompt, request.context),
                **options,
            )
        except APIError as exc:
            raise ProviderError(
                code=getattr(exc, "code", "openai_error") or "openai_error",
                message=str(exc),
                retryable=_is_retryable(exc),
                details={"status_code": getattr(exc, "status", None)},
            ) from exc
        except Exception as exc:  # pragma: no cover - network library edge cases
            raise ProviderError(
                code="openai_error",
                message=str(exc),
                retryable=_is_retryable(exc),
            ) from exc

        choice = response.choices[0]
        content = getattr(choice.message, "content", "") or ""
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return ProviderResponse(
            content=content,
            model=response.model,
            request_id=response.id,
            usage=usage,
            provider="openai",
        )

    async def aclose(self) -> None:
        self._client.close()
