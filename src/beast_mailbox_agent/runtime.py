"""Runtime orchestration for Beast Mailbox Agent."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from beast_mailbox_core import MailboxMessage
from beast_mailbox_core.redis_mailbox import RedisMailboxService
from redis.exceptions import ResponseError

from .config import AgentConfig, ConfigError
from .context import ContextStore, NullContextStore, RedisContextStore
from .handlers import PromptHandler
from .metrics import LoggingMetricsCollector, PrometheusMetricsCollector
from .providers.base import BaseProvider
from .providers.openai import OpenAIChatProvider

LOGGER = logging.getLogger("beast_mailbox_agent.runtime")


def _level_for(name: str) -> int:
    level = getattr(logging, name.upper(), logging.INFO)
    if isinstance(level, int):
        return level
    return logging.INFO


def create_provider(config: AgentConfig) -> BaseProvider:
    """Instantiate provider adapter specified in configuration."""
    if config.llm_provider.lower() == "openai":
        return OpenAIChatProvider(
            api_key=config.openai_api_key,
            default_model=config.model_name,
            timeout=config.request_timeout,
            default_options={
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
            },
        )
    raise ConfigError(f"Unsupported LLM provider: {config.llm_provider}")


class AgentRuntime:
    """Manage mailbox lifecycle and prompt processing."""

    def __init__(
        self,
        *,
        config: AgentConfig,
        mailbox_service: Optional[RedisMailboxService] = None,
        provider: Optional[BaseProvider] = None,
        prompt_handler: Optional[PromptHandler] = None,
        context_store: Optional[ContextStore] = None,
    ) -> None:
        self.config = config
        LOGGER.setLevel(_level_for(config.log_level))

        self.mailbox_service = mailbox_service or RedisMailboxService(
            config.agent_id,
            config.to_mailbox_config(),
        )

        if context_store is None:
            if config.context_enabled:
                context_store = RedisContextStore(
                    url=config.context_redis_url,
                    prefix=config.context_prefix,
                )
            else:
                context_store = NullContextStore()

        self._provider = provider
        self._metrics_collector = self._create_metrics_collector(config)

        if prompt_handler is None:
            if self._provider is None:
                self._provider = create_provider(config)
            prompt_handler = PromptHandler(
                config=config,
                provider=self._provider,
                send_response=self.mailbox_service.send_message,
                context_store=context_store,
                metrics=self._metrics_collector,
            )
        else:
            if self._provider is None and hasattr(prompt_handler, "_provider"):
                self._provider = getattr(prompt_handler, "_provider")

        self._prompt_handler = prompt_handler
        if hasattr(prompt_handler, "handle"):
            self._prompt_callback: Callable[[MailboxMessage], Awaitable[None]] = prompt_handler.handle  # type: ignore[attr-defined]
        else:
            self._prompt_callback = prompt_handler  # type: ignore[assignment]

        self._shutdown_event = asyncio.Event()
        self._started = False
        self._handler_registered = False

    async def start(self) -> None:
        """Start mailbox processing."""
        if self._started:
            return
        if not self._handler_registered:
            self.mailbox_service.register_handler(self._prompt_callback)
            self._handler_registered = True
        await self.mailbox_service.start()
        self._started = True
        await self._recover_pending_messages()
        LOGGER.info("Agent runtime started for agent_id=%s", self.config.agent_id)

    async def stop(self) -> None:
        """Stop mailbox processing and cleanup resources."""
        if not self._started:
            return
        try:
            await self.mailbox_service.stop()
        finally:
            if self._provider and hasattr(self._provider, "aclose"):
                try:
                    await self._provider.aclose()
                except Exception:  # pragma: no cover - provider cleanup best-effort
                    LOGGER.debug("Provider cleanup failed", exc_info=True)
            self._started = False
            self._shutdown_event.set()
            LOGGER.info("Agent runtime stopped for agent_id=%s", self.config.agent_id)

    def request_shutdown(self) -> None:
        """Signal the runtime loop to exit."""
        self._shutdown_event.set()

    async def run(self) -> None:
        """Start the runtime and run until shutdown is requested."""
        await self.start()
        try:
            await self._shutdown_event.wait()
        finally:
            await self.stop()


    def _create_metrics_collector(self, config: AgentConfig):
        if config.metrics_backend == "prometheus":
            return PrometheusMetricsCollector(
                agent_id=config.agent_id,
                port=config.metrics_port,
            )
        return LoggingMetricsCollector()

    async def _recover_pending_messages(self) -> None:
        """Claim and process any pending mailbox messages from previous runs."""
        LOGGER.info("Starting pending recovery for agent_id=%s", self.config.agent_id)
        client = getattr(self.mailbox_service, "_client", None)
        if client is None:
            await self.mailbox_service.connect()
            client = getattr(self.mailbox_service, "_client", None)
        if client is None:
            LOGGER.info("Pending recovery aborted - no Redis client for agent_id=%s", self.config.agent_id)
            return

        stream = self.mailbox_service.inbox_stream
        group = getattr(self.mailbox_service, "_consumer_group", None)
        consumer = getattr(self.mailbox_service, "_consumer_name", None)
        if not group or not consumer:
            LOGGER.info("Pending recovery aborted - missing group/consumer for agent_id=%s", self.config.agent_id)
            return

        recovered = 0
        try:
            cursor = "0-0"
            while True:
                cursor, entries, _ = await client.xautoclaim(
                    stream,
                    group,
                    consumer,
                    min_idle_time=0,
                    start_id=cursor,
                    count=50,
                )
                LOGGER.info(
                    "Pending recovery iteration for agent_id=%s: cursor=%s entries=%s",
                    self.config.agent_id,
                    cursor,
                    len(entries),
                )
                if not entries:
                    break
                for message_id, fields in entries:
                    mailbox_message = MailboxMessage.from_redis_fields(fields)
                    LOGGER.info(
                        "Recovering pending message_id=%s for agent_id=%s",
                        message_id,
                        self.config.agent_id,
                    )
                    await self._prompt_handler.handle(mailbox_message)
                    LOGGER.info(
                        "Completed recovery handling for message_id=%s agent_id=%s",
                        message_id,
                        self.config.agent_id,
                    )
                    await client.xack(stream, group, message_id)
                    recovered += 1
                if cursor == "0-0":
                    break
        except ResponseError as exc:
            if "NOGROUP" in str(exc) or "no such key" in str(exc):
                return
            LOGGER.warning("Pending recovery failed for agent_id=%s: %s", self.config.agent_id, exc)
        except Exception:
            LOGGER.exception("Unexpected error during pending recovery for agent_id=%s", self.config.agent_id)
        if recovered:
            LOGGER.info(
                "Recovered %s pending mailbox messages for agent_id=%s",
                recovered,
                self.config.agent_id,
            )


async def perform_healthcheck(
    config: AgentConfig,
    mailbox_factory: Optional[Callable[[AgentConfig], RedisMailboxService]] = None,
) -> bool:
    """Attempt to connect to the mailbox backend."""
    mailbox_factory = mailbox_factory or (lambda cfg: RedisMailboxService(cfg.agent_id, cfg.to_mailbox_config()))
    mailbox = mailbox_factory(config)
    try:
        await mailbox.connect()
        LOGGER.info("Healthcheck succeeded for agent_id=%s", config.agent_id)
        return True
    except Exception as exc:  # pragma: no cover - defensive logging
        LOGGER.warning("Healthcheck failed for agent_id=%s: %s", config.agent_id, exc)
        return False
    finally:
        if getattr(mailbox, "_running", False):
            try:
                await mailbox.stop()
            except Exception:
                LOGGER.debug("Error stopping mailbox after healthcheck", exc_info=True)
