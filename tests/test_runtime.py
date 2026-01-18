"""Runtime wiring tests for the Beast Mailbox Agent."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

from beast_mailbox_core import MailboxMessage

from beast_mailbox_agent.config import AgentConfig
from beast_mailbox_agent.metrics import PrometheusMetricsCollector
from beast_mailbox_agent.runtime import AgentRuntime, perform_healthcheck


def _config():
    return AgentConfig(
        agent_id="runtime-agent",
        redis_url="redis://localhost:6379/0",
        mailbox_stream="beast:mailbox:runtime-agent:in",
        mailbox_group="agent:runtime-agent",
        reply_stream="beast:mailbox:runtime-agent:out",
        stream_prefix="beast:mailbox",
        model_name="gpt-4o-mini",
        max_tokens=512,
        temperature=0.2,
        concurrency=2,
        retry_max=2,
        retry_backoff_base=0.01,
        context_enabled=False,
        context_ttl=900,
        context_prefix="beast:agent:runtime-agent:context",
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


class _StubMailbox:
    def __init__(self):
        self.handlers = []
        self.started = False
        self.stopped = False
        self.sent_messages = []
        self.connected = False

    def register_handler(self, handler):
        self.handlers.append(handler)

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def send_message(self, recipient, payload, **kwargs):
        self.sent_messages.append((recipient, payload))
        return "message-id"

    async def connect(self):
        self.connected = True


class _StubPromptHandler:
    def __init__(self):
        self.calls = []

    async def handle(self, message: MailboxMessage):
        self.calls.append(message)


@pytest.mark.asyncio
async def test_runtime_start_and_stop(monkeypatch):
    """Runtime should wire mailbox handler and manage lifecycle."""
    mailbox = _StubMailbox()
    prompt_handler = _StubPromptHandler()
    runtime = AgentRuntime(
        config=_config(),
        mailbox_service=mailbox,
        prompt_handler=prompt_handler,
    )

    await runtime.start()
    assert mailbox.started is True
    assert len(mailbox.handlers) == 1

    mailbox_message = MailboxMessage(
        message_id="msg",
        sender="sender",
        recipient="runtime-agent",
        payload={"prompt": "hello"},
    )
    await mailbox.handlers[0](mailbox_message)
    assert prompt_handler.calls[0] == mailbox_message

    await runtime.stop()
    assert mailbox.stopped is True


@pytest.mark.asyncio
async def test_perform_healthcheck_success(monkeypatch):
    """Healthcheck should validate mailbox connectivity."""
    calls = {}

    class HealthyMailbox(_StubMailbox):
        async def connect(self):
            calls["connect"] = True
            await asyncio.sleep(0)

    async def fake_provider_factory(config):
        return SimpleNamespace()

    result = await perform_healthcheck(
        _config(),
        mailbox_factory=lambda config: HealthyMailbox(),
    )

    assert result is True
    assert calls["connect"] is True


@pytest.mark.asyncio
async def test_runtime_run_until_shutdown():
    """Run helper should respect shutdown requests."""
    mailbox = _StubMailbox()
    prompt_handler = _StubPromptHandler()
    runtime = AgentRuntime(
        config=_config(),
        mailbox_service=mailbox,
        prompt_handler=prompt_handler,
    )

    task = asyncio.create_task(runtime.run())
    await asyncio.sleep(0)
    assert mailbox.started is True
    runtime.request_shutdown()
    await asyncio.sleep(0)
    await task
    assert mailbox.stopped is True


@pytest.mark.asyncio
async def test_runtime_uses_prometheus_metrics(monkeypatch):
    """Runtime should wire Prometheus metrics collector when configured."""

    class DummyProvider:
        async def generate(self, request):  # pragma: no cover - not invoked
            raise RuntimeError("not expected")

    monkeypatch.setattr(
        "beast_mailbox_agent.runtime.create_provider",
        lambda config: DummyProvider(),
    )

    config = replace(_config(), metrics_backend="prometheus", metrics_port=None)
    runtime = AgentRuntime(config=config, mailbox_service=_StubMailbox())

    assert isinstance(runtime._prompt_handler._metrics, PrometheusMetricsCollector)  # type: ignore[attr-defined]
