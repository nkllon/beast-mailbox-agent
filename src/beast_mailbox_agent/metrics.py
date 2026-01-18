"""Metrics collection primitives for Beast Mailbox Agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from prometheus_client import CollectorRegistry, Counter, Histogram, start_http_server


@dataclass
class MetricsEvent:
    """Structured metrics payload."""

    agent_id: str
    message_id: str
    sender: Optional[str]
    status: str
    provider: Optional[str]
    duration_ms: float
    attempts: int
    retryable: Optional[bool] = None
    error_code: Optional[str] = None


class MetricsCollector(Protocol):
    """Protocol for collecting metrics events."""

    def record(self, event: MetricsEvent) -> None:
        """Persist or emit the metrics event."""


class LoggingMetricsCollector(MetricsCollector):
    """Default metrics collector that logs structured events."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self._logger = logger or logging.getLogger("beast_mailbox_agent.metrics")

    def record(self, event: MetricsEvent) -> None:
        payload = {
            "agent_id": event.agent_id,
            "message_id": event.message_id,
            "sender": event.sender,
            "status": event.status,
            "provider": event.provider,
            "duration_ms": round(event.duration_ms, 3),
            "attempts": event.attempts,
            "retryable": event.retryable,
            "error_code": event.error_code,
        }
        self._logger.info("prompt_metrics", extra={"metrics": payload})


class PrometheusMetricsCollector(MetricsCollector):
    """Metrics collector backed by Prometheus client library."""

    def __init__(
        self,
        *,
        agent_id: str,
        port: Optional[int] = None,
        registry: Optional[CollectorRegistry] = None,
    ) -> None:
        self._agent_id = agent_id
        self._registry = registry or CollectorRegistry()
        self._events = Counter(
            "beast_prompt_events_total",
            "Total prompt processing events",
            ["agent_id", "status", "provider", "retryable", "error_code"],
            registry=self._registry,
        )
        self._duration = Histogram(
            "beast_prompt_duration_seconds",
            "Prompt handling duration",
            ["agent_id", "status", "provider"],
            registry=self._registry,
        )
        self._attempts = Histogram(
            "beast_prompt_attempts",
            "Prompt handling attempts",
            ["agent_id", "status"],
            registry=self._registry,
            buckets=(1, 2, 3, 4, 5, 10),
        )
        if port is not None:
            start_http_server(port, registry=self._registry)

    @property
    def registry(self) -> CollectorRegistry:
        return self._registry

    def record(self, event: MetricsEvent) -> None:
        provider = event.provider or "unknown"
        retryable = (
            "unknown"
            if event.retryable is None
            else str(bool(event.retryable)).lower()
        )
        error_code = event.error_code or "none"

        self._events.labels(
            agent_id=event.agent_id,
            status=event.status,
            provider=provider,
            retryable=retryable,
            error_code=error_code,
        ).inc()
        self._duration.labels(
            agent_id=event.agent_id,
            status=event.status,
            provider=provider,
        ).observe(max(event.duration_ms / 1000.0, 0.0))
        self._attempts.labels(
            agent_id=event.agent_id,
            status=event.status,
        ).observe(max(float(event.attempts), 0.0))
