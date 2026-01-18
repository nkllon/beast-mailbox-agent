"""Configuration utilities for the Beast Mailbox Agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from pathlib import Path

from beast_mailbox_core.redis_mailbox import MailboxConfig

# Load secrets from home directory first, then fall back to local lookups.
load_dotenv(Path.home() / ".env", override=False)
load_dotenv(override=False)


class ConfigError(ValueError):
    """Raised when configuration values are invalid or missing."""


def _as_bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes", "on"}


def _require(value: Optional[str], name: str) -> str:
    if value is None or value.strip() == "":
        raise ConfigError(f"{name} is required but was not provided")
    return value


@dataclass(frozen=True)
class AgentConfig:
    """Runtime configuration for the Beast Mailbox Agent."""

    agent_id: str
    redis_url: str
    mailbox_stream: str
    mailbox_group: str
    reply_stream: Optional[str]
    stream_prefix: str
    llm_provider: str
    openai_api_key: str
    model_name: str
    max_tokens: int
    temperature: float
    concurrency: int
    retry_max: int
    retry_backoff_base: float
    context_enabled: bool
    context_ttl: int
    context_prefix: str
    context_redis_url: str
    metrics_backend: str
    metrics_port: Optional[int]
    log_level: str
    poll_interval: float
    stream_maxlen: int
    request_timeout: float
    default_options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "AgentConfig":
        """Build configuration from environment variables."""
        env = env or os.environ

        agent_id = _require(env.get("BEAST_AGENT_ID"), "BEAST_AGENT_ID")
        redis_url = _require(env.get("BEAST_REDIS_URL"), "BEAST_REDIS_URL")
        openai_api_key = _require(env.get("BEAST_OPENAI_API_KEY"), "BEAST_OPENAI_API_KEY")

        stream_prefix = env.get("BEAST_STREAM_PREFIX", "beast:mailbox")
        mailbox_stream = env.get("BEAST_MAILBOX_STREAM", f"{stream_prefix}:{agent_id}:in")
        mailbox_group = env.get("BEAST_MAILBOX_GROUP", f"agent:{agent_id}")
        reply_stream = env.get("BEAST_REPLY_STREAM")
        llm_provider = env.get("BEAST_LLM_PROVIDER", "openai")
        model_name = env.get("BEAST_MODEL_NAME", "gpt-4o-mini")

        try:
            max_tokens = int(env.get("BEAST_MAX_TOKENS", "512"))
            temperature = float(env.get("BEAST_TEMPERATURE", "0.2"))
            concurrency = int(env.get("BEAST_CONCURRENCY", "1"))
            retry_max = int(env.get("BEAST_RETRY_MAX", "3"))
            retry_backoff_base = float(env.get("BEAST_RETRY_BACKOFF_BASE", "1.0"))
            context_enabled = _as_bool(env.get("BEAST_CONTEXT_ENABLED", "false"))
            context_ttl = int(env.get("BEAST_CONTEXT_TTL", "900"))
            context_prefix = env.get("BEAST_CONTEXT_PREFIX", f"beast:agent:{agent_id}:context")
            context_redis_url = env.get("BEAST_CONTEXT_REDIS_URL", redis_url)
            metrics_backend = env.get("BEAST_METRICS_BACKEND", "logging").strip().lower()
            metrics_port_raw = env.get("BEAST_METRICS_PORT")
            metrics_port = int(metrics_port_raw) if metrics_port_raw else None
            log_level = env.get("BEAST_LOG_LEVEL", "INFO").upper()
            poll_interval = float(env.get("BEAST_POLL_INTERVAL", "1.0"))
            stream_maxlen = int(env.get("BEAST_STREAM_MAXLEN", "1000"))
            request_timeout = float(env.get("BEAST_REQUEST_TIMEOUT", "60.0"))
        except ValueError as exc:
            raise ConfigError(f"Invalid numeric configuration: {exc}") from exc

        if concurrency < 1:
            raise ConfigError("BEAST_CONCURRENCY must be >= 1")
        if retry_max < 1:
            raise ConfigError("BEAST_RETRY_MAX must be >= 1")
        if max_tokens < 1:
            raise ConfigError("BEAST_MAX_TOKENS must be >= 1")
        if stream_maxlen < 1:
            raise ConfigError("BEAST_STREAM_MAXLEN must be >= 1")
        if poll_interval <= 0:
            raise ConfigError("BEAST_POLL_INTERVAL must be > 0")
        if retry_backoff_base < 0:
            raise ConfigError("BEAST_RETRY_BACKOFF_BASE must be >= 0")
        if metrics_backend not in {"logging", "prometheus"}:
            raise ConfigError("BEAST_METRICS_BACKEND must be 'logging' or 'prometheus'")
        if metrics_port is not None and metrics_port < 0:
            raise ConfigError("BEAST_METRICS_PORT must be >= 0 when provided")

        default_options: Dict[str, Any] = {
            "model": model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout": request_timeout,
        }

        return cls(
            agent_id=agent_id,
            redis_url=redis_url,
            mailbox_stream=mailbox_stream,
            mailbox_group=mailbox_group,
            reply_stream=reply_stream,
            stream_prefix=stream_prefix,
            llm_provider=llm_provider,
            openai_api_key=openai_api_key,
            model_name=model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            concurrency=concurrency,
            retry_max=retry_max,
            retry_backoff_base=retry_backoff_base,
            context_enabled=context_enabled,
            context_ttl=context_ttl,
            context_prefix=context_prefix,
            context_redis_url=context_redis_url,
            metrics_backend=metrics_backend,
            metrics_port=metrics_port,
            log_level=log_level,
            poll_interval=poll_interval,
            stream_maxlen=stream_maxlen,
            request_timeout=request_timeout,
            default_options=default_options,
        )

    def to_mailbox_config(self) -> MailboxConfig:
        """Translate agent configuration to MailboxConfig used by core library."""
        parsed = urlparse(self.redis_url)
        if parsed.scheme not in {"redis", "rediss"}:
            raise ConfigError("BEAST_REDIS_URL must use redis:// or rediss:// scheme")

        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        try:
            db = int((parsed.path or "0").lstrip("/") or "0")
        except ValueError as exc:
            raise ConfigError("Redis DB component must be numeric") from exc

        return MailboxConfig(
            host=host,
            port=port,
            db=db,
            password=parsed.password,
            stream_prefix=self.stream_prefix,
            max_stream_length=self.stream_maxlen,
            poll_interval=self.poll_interval,
        )

    def merged_options(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Return default provider options combined with overrides from a prompt."""
        merged = dict(self.default_options)
        if overrides:
            merged.update({k: v for k, v in overrides.items() if v is not None})
        return merged
