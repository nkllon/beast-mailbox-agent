"""Integration tests exercising runtime with a real Redis container."""

import asyncio
from contextlib import suppress

import pytest

import redis.asyncio as aioredis

from beast_mailbox_core import MailboxMessage
from beast_mailbox_core.redis_mailbox import MailboxConfig, RedisMailboxService

from beast_mailbox_agent.config import AgentConfig
from beast_mailbox_agent.context import NullContextStore
from beast_mailbox_agent.handlers import PromptHandler
from beast_mailbox_agent.metrics import LoggingMetricsCollector
from beast_mailbox_agent.providers.base import ProviderResponse, PromptRequest
from beast_mailbox_agent.runtime import AgentRuntime

try:
    from testcontainers.redis import RedisContainer
    from docker.errors import DockerException
except ModuleNotFoundError:  # pragma: no cover - handled in test skip
    RedisContainer = None  # type: ignore
    DockerException = Exception  # type: ignore


class _StubProvider:
    async def generate(self, request: PromptRequest) -> ProviderResponse:
        return ProviderResponse(
            content=f"Echo: {request.prompt}",
            model="stub-model",
            request_id="req-redis",
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            provider="stub",
        )


async def _wait_for(predicate, timeout: float = 5.0, interval: float = 0.05) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while not predicate():
        if asyncio.get_event_loop().time() >= deadline:
            raise asyncio.TimeoutError("condition not met in time")
        await asyncio.sleep(interval)


@pytest.mark.asyncio
async def test_runtime_handles_message_with_real_redis():
    if RedisContainer is None:
        pytest.skip("testcontainers not available")

    container = None
    try:
        container = RedisContainer("redis:7-alpine")
        container.start()
    except DockerException as exc:  # pragma: no cover - environment specific
        pytest.skip(f"Docker unavailable: {exc}")

    runtime: AgentRuntime | None = None
    sender_service: RedisMailboxService | None = None
    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        redis_url = f"redis://{host}:{port}/0"
        agent_id = "integration-agent"
        config = AgentConfig(
            agent_id=agent_id,
            redis_url=redis_url,
            mailbox_stream=f"beast:mailbox:{agent_id}:in",
            mailbox_group=f"agent:{agent_id}",
            reply_stream=None,
            stream_prefix="beast:mailbox",
            llm_provider="openai",
            openai_api_key="test-key",
            model_name="stub-model",
            max_tokens=256,
            temperature=0.1,
            concurrency=2,
            retry_max=3,
            retry_backoff_base=0.01,
            context_enabled=False,
            context_ttl=0,
            context_prefix=f"beast:agent:{agent_id}:context",
            context_redis_url=redis_url,
            metrics_backend="logging",
            metrics_port=None,
            log_level="INFO",
            poll_interval=0.1,
            stream_maxlen=1024,
            request_timeout=30.0,
            default_options={"model": "stub-model", "max_tokens": 256, "temperature": 0.1},
        )

        mailbox_config = config.to_mailbox_config()
        mailbox_service = RedisMailboxService(agent_id, mailbox_config)
        provider = _StubProvider()
        prompt_handler = PromptHandler(
            config=config,
            provider=provider,
            send_response=mailbox_service.send_message,
            context_store=NullContextStore(),
            metrics=LoggingMetricsCollector(),
        )

        runtime = AgentRuntime(
            config=config,
            mailbox_service=mailbox_service,
            provider=provider,
            prompt_handler=prompt_handler,
        )

        sender_config = MailboxConfig(
            host=mailbox_config.host,
            port=mailbox_config.port,
            password=mailbox_config.password,
            db=mailbox_config.db,
            stream_prefix=config.stream_prefix,
            poll_interval=0.1,
        )
        sender_service = RedisMailboxService("integration-sender", sender_config)

        received: list[MailboxMessage] = []

        async def capture_response(msg: MailboxMessage) -> None:
            received.append(msg)

        sender_service.register_handler(capture_response)

        await sender_service.start()
        await runtime.start()

        await sender_service.send_message(
            agent_id,
            {
                "prompt": "ping",
                "metadata": {"request_id": "abc"},
            },
        )

        await _wait_for(lambda: received)

        assert received[0].payload["status"] == "success"
        assert received[0].payload["response"]["content"] == "Echo: ping"
        assert received[0].payload["metadata"]["request_id"] == "abc"

    finally:
        if runtime is not None:
            await runtime.stop()
        if sender_service is not None:
            await sender_service.stop()
        with suppress(Exception):
            container.stop()


@pytest.mark.asyncio
async def test_runtime_recovers_pending_entries():
    if RedisContainer is None:
        pytest.skip("testcontainers not available")

    import logging

    logging.getLogger("beast_mailbox_agent.runtime").setLevel(logging.DEBUG)

    container = None
    client = None
    runtime: AgentRuntime | None = None
    sender_service: RedisMailboxService | None = None
    try:
        container = RedisContainer("redis:7-alpine")
        container.start()

        host = container.get_container_host_ip()
        port = container.get_exposed_port(container.port)
        redis_url = f"redis://{host}:{port}/0"
        agent_id = "integration-pending"
        config = AgentConfig(
            agent_id=agent_id,
            redis_url=redis_url,
            mailbox_stream=f"beast:mailbox:{agent_id}:in",
            mailbox_group=f"agent:{agent_id}",
            reply_stream=None,
            stream_prefix="beast:mailbox",
            llm_provider="openai",
            openai_api_key="test-key",
            model_name="stub-model",
            max_tokens=256,
            temperature=0.1,
            concurrency=2,
            retry_max=3,
            retry_backoff_base=0.01,
            context_enabled=False,
            context_ttl=0,
            context_prefix=f"beast:agent:{agent_id}:context",
            context_redis_url=redis_url,
            metrics_backend="logging",
            metrics_port=None,
            log_level="INFO",
            poll_interval=0.1,
            stream_maxlen=1024,
            request_timeout=30.0,
            default_options={"model": "stub-model", "max_tokens": 256, "temperature": 0.1},
        )

        mailbox_config = config.to_mailbox_config()
        mailbox_service = RedisMailboxService(agent_id, mailbox_config)
        provider = _StubProvider()
        runtime = AgentRuntime(
            config=config,
            mailbox_service=mailbox_service,
            provider=provider,
        )

        sender_config = MailboxConfig(
            host=mailbox_config.host,
            port=mailbox_config.port,
            password=mailbox_config.password,
            db=mailbox_config.db,
            stream_prefix=config.stream_prefix,
            poll_interval=0.1,
        )
        sender_service = RedisMailboxService("integration-sender", sender_config)
        responses: list[MailboxMessage] = []

        async def capture_response(msg: MailboxMessage) -> None:
            responses.append(msg)

        sender_service.register_handler(capture_response)

        client = aioredis.from_url(redis_url, decode_responses=False)
        stream = config.mailbox_stream
        group = mailbox_service._consumer_group  # use service's actual group naming

        try:
            await client.xgroup_create(name=stream, groupname=group, id="0-0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

        pending_message = MailboxMessage(
            message_id="pending-1",
            sender="integration-sender",
            recipient=agent_id,
            payload={"prompt": "recover", "metadata": {"request_id": "pending"}},
        )
        await client.xadd(stream, pending_message.to_redis_fields())

        await client.xreadgroup(
            groupname=group,
            consumername="stalled-consumer",
            streams={stream: ">"},
            count=1,
        )

        pending_before = await client.xpending(stream, group)
        assert pending_before["pending"] == 1

        await sender_service.start()
        await runtime.start()

        await asyncio.sleep(0.1)
        pending_after_start = await client.xpending(stream, group)
        assert pending_after_start["pending"] <= 1

        await _wait_for(lambda: responses)

        assert responses[0].payload["status"] == "success"
        assert responses[0].payload["response"]["content"] == "Echo: recover"

        pending_info = await client.xpending(stream, group)
        assert pending_info["pending"] == 0

    finally:
        if runtime is not None:
            await runtime.stop()
        if sender_service is not None:
            await sender_service.stop()
        if client is not None:
            await client.aclose()
        with suppress(Exception):
            container.stop()
