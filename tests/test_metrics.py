"""Unit tests for metrics collectors."""

from prometheus_client import CollectorRegistry

from beast_mailbox_agent.metrics import (
    LoggingMetricsCollector,
    MetricsEvent,
    PrometheusMetricsCollector,
)


def test_logging_metrics_collector_logs(monkeypatch):
    logs = {}

    class _Logger:
        def info(self, name, extra=None):
            logs["name"] = name
            logs["extra"] = extra

    collector = LoggingMetricsCollector(logger=_Logger())
    collector.record(
        MetricsEvent(
            agent_id="agent-a",
            message_id="msg-1",
            sender="client",
            status="success",
            provider="stub",
            duration_ms=12.5,
            attempts=1,
            retryable=None,
            error_code=None,
        )
    )

    assert logs["name"] == "prompt_metrics"
    assert logs["extra"]["metrics"]["status"] == "success"


def test_prometheus_metrics_collector_records_values():
    registry = CollectorRegistry()
    collector = PrometheusMetricsCollector(agent_id="agent-b", registry=registry)

    collector.record(
        MetricsEvent(
            agent_id="agent-b",
            message_id="msg-1",
            sender="client",
            status="success",
            provider="stub",
            duration_ms=100.0,
            attempts=1,
            retryable=None,
            error_code=None,
        )
    )

    collector.record(
        MetricsEvent(
            agent_id="agent-b",
            message_id="msg-2",
            sender="client",
            status="error",
            provider=None,
            duration_ms=200.0,
            attempts=3,
            retryable=False,
            error_code="rate_limited",
        )
    )

    success_total = registry.get_sample_value(
        "beast_prompt_events_total",
        labels={
            "agent_id": "agent-b",
            "status": "success",
            "provider": "stub",
            "retryable": "unknown",
            "error_code": "none",
        },
    )
    assert success_total == 1.0

    error_total = registry.get_sample_value(
        "beast_prompt_events_total",
        labels={
            "agent_id": "agent-b",
            "status": "error",
            "provider": "unknown",
            "retryable": "false",
            "error_code": "rate_limited",
        },
    )
    assert error_total == 1.0

    duration_sum = registry.get_sample_value(
        "beast_prompt_duration_seconds_sum",
        labels={"agent_id": "agent-b", "status": "success", "provider": "stub"},
    )
    assert duration_sum == 0.1

    attempts_sum = registry.get_sample_value(
        "beast_prompt_attempts_sum",
        labels={"agent_id": "agent-b", "status": "error"},
    )
    assert attempts_sum == 3.0
