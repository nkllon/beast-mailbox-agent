"""Message handling pipeline for the Beast Mailbox Agent."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, Optional

from beast_mailbox_core import MailboxMessage

from .config import AgentConfig
from .context import ContextStore, NullContextStore
from .metrics import LoggingMetricsCollector, MetricsCollector, MetricsEvent
from .providers.base import ProviderError, ProviderResponse, PromptRequest

SendResponseFn = Callable[..., Awaitable[str]]


class PromptHandler:
    """Coordinate prompt validation, provider invocation, and response emission."""

    RESPONSE_MESSAGE_TYPE = "agent_response"

    def __init__(
        self,
        *,
        config: AgentConfig,
        provider,
        send_response: SendResponseFn,
        context_store: Optional[ContextStore] = None,
        logger: Optional[logging.Logger] = None,
        metrics: Optional[MetricsCollector] = None,
    ):
        self._config = config
        self._provider = provider
        self._send_response = send_response
        self._context_store = context_store or NullContextStore()
        self._logger = logger or logging.getLogger("beast_mailbox_agent.prompt_handler")
        self._semaphore = asyncio.Semaphore(config.concurrency)
        self._metrics = metrics or LoggingMetricsCollector()

    async def handle(self, message: MailboxMessage) -> None:
        """Entry point used by the mailbox processor."""
        async with self._semaphore:
            try:
                await self._process_message(message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.exception("Unhandled error processing mailbox message %s: %s", message.message_id, exc)

    async def _process_message(self, message: MailboxMessage) -> None:
        start = perf_counter()
        payload = message.payload or {}
        prompt_value = payload.get("prompt")
        if not isinstance(prompt_value, str) or prompt_value.strip() == "":
            await self._send_error(
                message,
                code="invalid_payload",
                error_message="Payload must include non-empty 'prompt' field",
                retryable=False,
                metadata=payload.get("metadata"),
            )
            self._metrics.record(
                MetricsEvent(
                    agent_id=self._config.agent_id,
                    message_id=message.message_id,
                    sender=message.sender,
                    status="error",
                    provider=None,
                    duration_ms=(perf_counter() - start) * 1000,
                    attempts=0,
                    retryable=False,
                    error_code="invalid_payload",
                )
            )
            return

        options = payload.get("options")
        merged_options = self._config.merged_options(options if isinstance(options, dict) else None)
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        thread_id = payload.get("thread_id")
        reply_to = payload.get("reply_to") or message.sender

        context = payload.get("context") if isinstance(payload.get("context"), dict) else None
        if self._config.context_enabled and thread_id:
            stored = await self._context_store.get(self._context_key(thread_id))
            if stored:
                context = stored

        request = PromptRequest(
            prompt=prompt_value,
            options=merged_options,
            metadata=metadata,
            context=context,
            thread_id=thread_id,
            sender=message.sender,
            message_id=message.message_id,
        )

        success, outcome, attempts = await self._invoke_provider_with_retry(request, message)
        if not success:
            error: ProviderError = outcome  # type: ignore[assignment]
            await self._send_error(
                message,
                code=error.code,
                error_message=error.message,
                retryable=error.retryable,
                metadata=metadata,
                details=error.details,
            )
            self._metrics.record(
                MetricsEvent(
                    agent_id=self._config.agent_id,
                    message_id=message.message_id,
                    sender=message.sender,
                    status="error",
                    provider=None,
                    duration_ms=(perf_counter() - start) * 1000,
                    attempts=attempts,
                    retryable=error.retryable,
                    error_code=error.code,
                )
            )
            return

        provider_response: ProviderResponse = outcome  # type: ignore[assignment]
        await self._send_success(message, provider_response, reply_to, metadata, thread_id)
        self._metrics.record(
            MetricsEvent(
                agent_id=self._config.agent_id,
                message_id=message.message_id,
                sender=message.sender,
                status="success",
                provider=provider_response.provider,
                duration_ms=(perf_counter() - start) * 1000,
                attempts=attempts,
            )
        )

        if self._config.context_enabled and thread_id:
            await self._update_context(thread_id, context, prompt_value, provider_response.content)

    async def _invoke_provider_with_retry(
        self,
        request: PromptRequest,
        message: MailboxMessage,
    ) -> tuple[bool, ProviderResponse | ProviderError, int]:
        attempt = 0
        while True:
            attempt += 1
            try:
                self._logger.debug(
                    "Processing prompt message %s attempt %s",
                    message.message_id,
                    attempt,
                )
                response = await self._provider.generate(request)
                return True, response, attempt
            except ProviderError as exc:
                self._logger.warning(
                    "Provider error for message %s: %s (retryable=%s, attempt=%s/%s)",
                    message.message_id,
                    exc.code,
                    exc.retryable,
                    attempt,
                    self._config.retry_max,
                )
                if not exc.retryable or attempt >= self._config.retry_max:
                    return False, exc, attempt
                await self._backoff(attempt)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._logger.exception("Unexpected provider exception for %s: %s", message.message_id, exc)
                return False, ProviderError(
                    code="unhandled_error",
                    message="Unexpected provider error",
                    retryable=False,
                    details={"exception_type": type(exc).__name__},
                ), attempt

    async def _backoff(self, attempt: int) -> None:
        delay = self._config.retry_backoff_base * (2 ** (attempt - 1))
        if delay > 0:
            await asyncio.sleep(delay)

    async def _send_success(
        self,
        message: MailboxMessage,
        provider_response: ProviderResponse,
        recipient: str,
        metadata: Dict[str, Any],
        thread_id: Optional[str],
    ) -> None:
        payload = {
            "status": "success",
            "response": {
                "content": provider_response.content,
                "model": provider_response.model,
                "usage": provider_response.usage,
                "provider": provider_response.provider,
            },
            "request_id": provider_response.request_id,
            "message_id": message.message_id,
            "correlation": {
                "sender": message.sender,
                "thread_id": thread_id,
            },
            "metadata": metadata or {},
        }
        await self._send_response(
            recipient,
            payload,
            message_type=self.RESPONSE_MESSAGE_TYPE,
        )

    async def _send_error(
        self,
        message: MailboxMessage,
        *,
        code: str,
        error_message: str,
        retryable: bool,
        metadata: Optional[Dict[str, Any]] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload = {
            "status": "error",
            "error": {
                "code": code,
                "message": error_message,
                "retryable": retryable,
                "details": details or {},
            },
            "message_id": message.message_id,
            "correlation": {
                "sender": message.sender,
            },
            "metadata": metadata or {},
        }
        await self._send_response(
            message.sender,
            payload,
            message_type=self.RESPONSE_MESSAGE_TYPE,
        )

    async def _update_context(
        self,
        thread_id: str,
        context: Optional[Dict[str, Any]],
        prompt: str,
        response_text: str,
    ) -> None:
        key = self._context_key(thread_id)
        context = context or {"messages": []}
        messages = context.setdefault("messages", [])
        if isinstance(messages, list):
            messages.append({"role": "user", "content": prompt})
            messages.append({"role": "assistant", "content": response_text})
        await self._context_store.set(key, context, ttl=self._config.context_ttl)

    def _context_key(self, thread_id: str) -> str:
        return f"{self._config.agent_id}:{thread_id}"
