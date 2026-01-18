"""Tests for prompt handling pipeline."""

import asyncio

import pytest

from beast_mailbox_core import MailboxMessage

from beast_mailbox_agent.config import AgentConfig
from beast_mailbox_agent.context import InMemoryContextStore
from beast_mailbox_agent.handlers import PromptHandler
from beast_mailbox_agent.metrics import MetricsEvent
from beast_mailbox_agent.providers.base import (
    ProviderError,
    ProviderResponse,
    PromptRequest,
)


class _SuccessfulProvider:
    def __init__(self):
        self.requests = []

    async def generate(self, request: PromptRequest) -> ProviderResponse:
        self.requests.append(request)
        return ProviderResponse(
            content="Hello world",
            model="test-model",
            request_id="req-1",
            usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
            provider="stub",
        )


class _FailingProvider:
    def __init__(self, retryable: bool):
        self.retryable = retryable
        self.calls = 0

    async def generate(self, request: PromptRequest) -> ProviderResponse:
        self.calls += 1
        raise ProviderError(
            code="llm_error",
            message="provider failure",
            retryable=self.retryable,
        )


def _make_config(**overrides):
    base = dict(
        agent_id="agent-test",
        redis_url="redis://localhost:6379/0",
        mailbox_stream="beast:mailbox:agent-test:in",
        mailbox_group="agent:agent-test",
        reply_stream="beast:mailbox:agent-test:out",
        stream_prefix="beast:mailbox",
        model_name="gpt-4o-mini",
        max_tokens=512,
        temperature=0.2,
        concurrency=1,
        retry_max=2,
        retry_backoff_base=0.01,
        context_enabled=False,
        context_ttl=900,
        context_prefix="beast:agent:agent-test:context",
        context_redis_url="redis://localhost:6379/0",
        metrics_backend="logging",
        metrics_port=None,
        log_level="INFO",
        poll_interval=1.0,
        stream_maxlen=1000,
        request_timeout=30.0,
        llm_provider="openai",
        openai_api_key="dummy",
        default_options={"model": "gpt-4o-mini", "max_tokens": 512, "temperature": 0.2},
    )
    base.update(overrides)
    return AgentConfig(**base)


def _make_message(payload):
    return MailboxMessage(
        message_id="msg-1",
        sender="sender-service",
        recipient="agent-test",
        payload=payload,
    )


@pytest.mark.asyncio
async def test_prompt_handler_successful_flow(monkeypatch):
    """Valid prompt should invoke provider and send structured response."""
    provider = _SuccessfulProvider()
    responses = []
    metrics = _RecorderMetrics()

    async def record_response(recipient, payload, **kwargs):
        responses.append((recipient, payload))
        return "resp-1"

    handler = PromptHandler(
        config=_make_config(),
        provider=provider,
        send_response=record_response,
        metrics=metrics,
    )

    message = _make_message(
        {
            "prompt": "Explain Beast.",
            "thread_id": "thread-123",
            "options": {"temperature": 0.5},
            "metadata": {"trace_id": "abc"},
        }
    )

    await handler.handle(message)

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.prompt == "Explain Beast."
    assert request.options["temperature"] == 0.5
    assert responses[0][0] == "sender-service"
    payload = responses[0][1]
    assert payload["status"] == "success"
    assert payload["response"]["content"] == "Hello world"
    assert payload["correlation"]["thread_id"] == "thread-123"
    assert payload["metadata"]["trace_id"] == "abc"
    assert metrics.events[-1].status == "success"
    assert metrics.events[-1].attempts == 1


@pytest.mark.asyncio
async def test_prompt_handler_handles_non_retryable_error(monkeypatch):
    """Provider errors should result in error responses without retries."""
    provider = _FailingProvider(retryable=False)
    responses = []
    metrics = _RecorderMetrics()

    async def record_response(recipient, payload, **kwargs):
        responses.append(payload)

    handler = PromptHandler(
        config=_make_config(),
        provider=provider,
        send_response=record_response,
        metrics=metrics,
    )

    message = _make_message({"prompt": "bad prompt"})

    await handler.handle(message)

    assert provider.calls == 1
    assert responses[0]["status"] == "error"
    assert responses[0]["error"]["code"] == "llm_error"
    assert responses[0]["error"]["retryable"] is False
    assert metrics.events[-1].status == "error"
    assert metrics.events[-1].error_code == "llm_error"


@pytest.mark.asyncio
async def test_prompt_handler_retries_retryable_errors(monkeypatch):
    """Retryable errors should be attempted up to retry_max."""
    provider = _FailingProvider(retryable=True)
    responses = []
    metrics = _RecorderMetrics()

    async def record_response(recipient, payload, **kwargs):
        responses.append(payload)

    handler = PromptHandler(
        config=_make_config(retry_max=3, retry_backoff_base=0),
        provider=provider,
        send_response=record_response,
        metrics=metrics,
    )

    message = _make_message({"prompt": "try again"})

    # Avoid actual sleep in tests
    async def _instant_sleep(_):
        return None

    monkeypatch.setattr("asyncio.sleep", _instant_sleep)

    await handler.handle(message)

    assert provider.calls == 3
    assert responses[0]["status"] == "error"
    assert responses[0]["error"]["retryable"] is True
    assert metrics.events[-1].attempts == 3


@pytest.mark.asyncio
async def test_prompt_handler_validates_payload(monkeypatch):
    """Malformed payloads should yield an actionable error response."""
    provider = _SuccessfulProvider()
    responses = []
    metrics = _RecorderMetrics()

    async def record_response(recipient, payload, **kwargs):
        responses.append(payload)

    handler = PromptHandler(
        config=_make_config(),
        provider=provider,
        send_response=record_response,
        metrics=metrics,
    )

    message = _make_message({"text": "missing prompt"})

    await handler.handle(message)

    assert responses[0]["status"] == "error"
    assert responses[0]["error"]["code"] == "invalid_payload"
    assert provider.requests == []
    assert metrics.events[-1].error_code == "invalid_payload"


@pytest.mark.asyncio
async def test_prompt_handler_enforces_concurrency_limit():
    """Concurrency semaphore should prevent more than configured concurrent calls."""
    active = 0
    peak = 0

    class SlowProvider:
        async def generate(self, request: PromptRequest) -> ProviderResponse:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return ProviderResponse(
                content="ok",
                model="model",
                request_id="req",
                usage={},
                provider="stub",
            )

    responses = []
    metrics = _RecorderMetrics()

    async def record_response(recipient, payload, **kwargs):
        responses.append(payload)

    handler = PromptHandler(
        config=_make_config(concurrency=1),
        provider=SlowProvider(),
        send_response=record_response,
        metrics=metrics,
    )

    message1 = _make_message({"prompt": "first"})
    message2 = _make_message({"prompt": "second"})

    await asyncio.gather(handler.handle(message1), handler.handle(message2))

    assert peak == 1
    assert len(responses) == 2
    assert metrics.events[0].status == "success"
    assert metrics.events[1].status == "success"


@pytest.mark.asyncio
async def test_prompt_handler_updates_context_store():
    """Context store should capture conversation history when enabled."""
    provider = _SuccessfulProvider()
    store = InMemoryContextStore()
    responses = []
    metrics = _RecorderMetrics()

    async def record_response(recipient, payload, **kwargs):
        responses.append(payload)

    handler = PromptHandler(
        config=_make_config(context_enabled=True),
        provider=provider,
        send_response=record_response,
        context_store=store,
        metrics=metrics,
    )

    message = _make_message({"prompt": "Hello there", "thread_id": "thread-xyz"})
    await handler.handle(message)

    stored = await store.get("agent-test:thread-xyz")
    assert stored is not None
    assert stored["messages"][0]["content"] == "Hello there"
    assert stored["messages"][-1]["content"] == "Hello world"
    assert metrics.events[-1].status == "success"


@pytest.mark.asyncio
async def test_prompt_handler_handles_unexpected_exception():
    """Unexpected provider exceptions should surface as unhandled_error."""

    class ExplodingProvider:
        async def generate(self, request: PromptRequest) -> ProviderResponse:
            raise RuntimeError("boom")

    responses = []
    metrics = _RecorderMetrics()

    async def record_response(recipient, payload, **kwargs):
        responses.append(payload)

    handler = PromptHandler(
        config=_make_config(),
        provider=ExplodingProvider(),
        send_response=record_response,
        metrics=metrics,
    )

    message = _make_message({"prompt": "trigger"})
    await handler.handle(message)

    assert responses[0]["error"]["code"] == "unhandled_error"
    assert metrics.events[-1].error_code == "unhandled_error"
class _RecorderMetrics:
    def __init__(self):
        self.events: list[MetricsEvent] = []

    def record(self, event: MetricsEvent) -> None:
        self.events.append(event)
