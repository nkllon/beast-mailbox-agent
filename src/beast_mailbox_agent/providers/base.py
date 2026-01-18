"""Provider abstractions for LLM integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass
class PromptRequest:
    """Normalized prompt request passed to provider adapters."""

    prompt: str
    options: Dict[str, Any]
    metadata: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    thread_id: Optional[str] = None
    sender: Optional[str] = None
    message_id: Optional[str] = None


@dataclass
class ProviderResponse:
    """Structured provider output used by the agent."""

    content: str
    model: str
    request_id: str
    usage: Dict[str, Any]
    provider: str


class ProviderError(Exception):
    """Standard error raised by provider adapters."""

    def __init__(self, code: str, message: str, retryable: bool = False, *, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class BaseProvider(Protocol):
    """Protocol describing provider behaviour."""

    async def generate(self, request: PromptRequest) -> ProviderResponse:
        """Produce a model response for the given prompt."""

    async def aclose(self) -> None:  # pragma: no cover - optional hook
        """Optional async cleanup hook."""
