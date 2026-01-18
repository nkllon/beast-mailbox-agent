"""Tests for Beast Mailbox Agent configuration handling."""

import pytest

from beast_mailbox_agent.config import AgentConfig, ConfigError


def _apply_env(monkeypatch, pairs):
    for key, value in pairs.items():
        monkeypatch.setenv(key, value)


def test_config_from_env_with_defaults(monkeypatch):
    """Ensure required environment variables produce a valid configuration."""
    _apply_env(
        monkeypatch,
        {
            "BEAST_AGENT_ID": "agent-1",
            "BEAST_REDIS_URL": "redis://localhost:6379/0",
            "BEAST_OPENAI_API_KEY": "test-key",
        },
    )

    config = AgentConfig.from_env()

    assert config.agent_id == "agent-1"
    assert config.redis_url == "redis://localhost:6379/0"
    assert config.mailbox_stream == "beast:mailbox:agent-1:in"
    assert config.mailbox_group == "agent:agent-1"
    assert config.model_name == "gpt-4o-mini"
    assert config.max_tokens == 512
    assert config.temperature == 0.2
    assert config.concurrency == 1
    mailbox_cfg = config.to_mailbox_config()
    assert mailbox_cfg.host == "localhost"
    assert mailbox_cfg.port == 6379
    assert mailbox_cfg.db == 0
    assert mailbox_cfg.stream_prefix == "beast:mailbox"
    assert config.context_prefix == "beast:agent:agent-1:context"
    assert config.context_redis_url == "redis://localhost:6379/0"
    assert config.metrics_backend == "logging"
    assert config.metrics_port is None


def test_config_from_env_overrides(monkeypatch):
    """Custom environment values should override defaults."""
    _apply_env(
        monkeypatch,
        {
            "BEAST_AGENT_ID": "agent-2",
            "BEAST_REDIS_URL": "redis://redis.internal:6380/2",
            "BEAST_MAILBOX_STREAM": "custom:inbox",
            "BEAST_MAILBOX_GROUP": "custom-group",
            "BEAST_OPENAI_API_KEY": "test-key",
            "BEAST_MODEL_NAME": "gpt-4o-large",
            "BEAST_CONCURRENCY": "3",
            "BEAST_RETRY_MAX": "5",
            "BEAST_RETRY_BACKOFF_BASE": "0.5",
            "BEAST_CONTEXT_ENABLED": "true",
            "BEAST_CONTEXT_TTL": "1200",
            "BEAST_CONTEXT_PREFIX": "ctx:prefix",
            "BEAST_CONTEXT_REDIS_URL": "redis://context:6379/1",
            "BEAST_METRICS_BACKEND": "prometheus",
            "BEAST_METRICS_PORT": "9100",
            "BEAST_LOG_LEVEL": "DEBUG",
            "BEAST_POLL_INTERVAL": "1.5",
            "BEAST_STREAM_MAXLEN": "4096",
        },
    )

    config = AgentConfig.from_env()

    assert config.agent_id == "agent-2"
    assert config.mailbox_stream == "custom:inbox"
    assert config.mailbox_group == "custom-group"
    assert config.model_name == "gpt-4o-large"
    assert config.concurrency == 3
    assert config.retry_max == 5
    assert config.retry_backoff_base == pytest.approx(0.5)
    assert config.context_enabled is True
    assert config.context_ttl == 1200
    assert config.context_prefix == "ctx:prefix"
    assert config.context_redis_url == "redis://context:6379/1"
    assert config.metrics_backend == "prometheus"
    assert config.metrics_port == 9100
    assert config.log_level == "DEBUG"
    assert config.poll_interval == pytest.approx(1.5)
    assert config.stream_maxlen == 4096


@pytest.mark.parametrize(
    "env_key",
    ["BEAST_AGENT_ID", "BEAST_REDIS_URL", "BEAST_OPENAI_API_KEY"],
)
def test_config_missing_required(monkeypatch, env_key):
    """Missing required values should raise an explicit ConfigError."""
    base_env = {
        "BEAST_AGENT_ID": "agent-1",
        "BEAST_REDIS_URL": "redis://localhost:6379/0",
        "BEAST_OPENAI_API_KEY": "test-key",
    }
    base_env.pop(env_key)

    _apply_env(monkeypatch, base_env)

    with pytest.raises(ConfigError) as exc:
        AgentConfig.from_env()

    assert env_key in str(exc.value)


def test_config_validation_bounds(monkeypatch):
    """Invalid numeric bounds should trigger ConfigError."""
    _apply_env(
        monkeypatch,
        {
            "BEAST_AGENT_ID": "agent-1",
            "BEAST_REDIS_URL": "redis://localhost:6379/0",
            "BEAST_OPENAI_API_KEY": "test-key",
            "BEAST_CONCURRENCY": "0",
        },
    )

    with pytest.raises(ConfigError) as exc:
        AgentConfig.from_env()

    assert "BEAST_CONCURRENCY" in str(exc.value)
