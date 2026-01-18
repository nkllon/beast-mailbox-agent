"""CLI command tests for Beast Mailbox Agent."""

from typer.testing import CliRunner

from beast_mailbox_agent.cli import app
from beast_mailbox_agent.config import ConfigError


def _baseline_env():
    return {
        "BEAST_AGENT_ID": "agent-cli",
        "BEAST_REDIS_URL": "redis://localhost:6379/0",
        "BEAST_OPENAI_API_KEY": "test-key",
    }


def test_cli_run_invokes_runtime(monkeypatch):
    """`beast-agent run` should instantiate and execute the runtime."""
    runner = CliRunner()
    calls = []

    class FakeRuntime:
        def __init__(self, config):
            calls.append(("init", config.agent_id))
            self.config = config

        async def run(self):
            calls.append(("run", self.config.agent_id))

        def request_shutdown(self):
            calls.append(("shutdown-request", self.config.agent_id))

    monkeypatch.setenv("BEAST_AGENT_ID", "agent-cli")
    monkeypatch.setenv("BEAST_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("BEAST_OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("beast_mailbox_agent.cli.AgentRuntime", FakeRuntime)

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 0
    assert calls == [
        ("init", "agent-cli"),
        ("run", "agent-cli"),
    ]


def test_cli_healthcheck(monkeypatch):
    """`beast-agent healthcheck` should report status based on runtime check."""
    runner = CliRunner()

    async def fake_healthcheck(config):
        return True

    monkeypatch.setattr(
        "beast_mailbox_agent.cli.perform_healthcheck",
        fake_healthcheck,
    )
    env = _baseline_env()

    result = runner.invoke(app, ["healthcheck"], env=env)

    assert result.exit_code == 0
    assert "healthy" in result.stdout.lower()


def test_cli_run_configuration_error(monkeypatch):
    """Configuration errors should surface with exit code 2."""
    runner = CliRunner()

    def _raise_config_error():
        raise ConfigError("bad config")

    monkeypatch.setattr(
        "beast_mailbox_agent.cli.AgentConfig.from_env",
        classmethod(lambda cls: _raise_config_error()),
    )

    result = runner.invoke(app, ["run"])

    assert result.exit_code == 2
    assert "configuration error" in result.stdout.lower()


def test_cli_healthcheck_failure(monkeypatch):
    """Healthcheck failures should exit non-zero."""
    runner = CliRunner()

    async def _failing_healthcheck(config):
        return False

    monkeypatch.setattr(
        "beast_mailbox_agent.cli.perform_healthcheck",
        _failing_healthcheck,
    )
    env = _baseline_env()

    result = runner.invoke(app, ["healthcheck"], env=env)

    assert result.exit_code == 1
    assert "unhealthy" in result.stdout.lower()
