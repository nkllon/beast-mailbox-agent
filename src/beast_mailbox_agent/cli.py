"""CLI entry point for Beast Mailbox Agent."""

from __future__ import annotations

import asyncio
import signal
from typing import Callable

import typer

from .config import AgentConfig, ConfigError
from .runtime import AgentRuntime, perform_healthcheck

app = typer.Typer(help="Run and manage the Beast Mailbox Agent.")


def _load_config() -> AgentConfig:
    try:
        return AgentConfig.from_env()
    except ConfigError as exc:
        typer.secho(f"Configuration error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc


def _install_signal_handlers(runtime: AgentRuntime) -> Callable[[], None]:
    loop = asyncio.get_running_loop()

    def _stop(*_: object) -> None:
        runtime.request_shutdown()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    def _restore() -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.remove_signal_handler(sig)
            except NotImplementedError:
                pass

    return _restore


@app.command()
def run() -> None:
    """Run the Beast Mailbox Agent until interrupted."""
    config = _load_config()
    runtime = AgentRuntime(config=config)

    async def _runner() -> None:
        restore_signals = _install_signal_handlers(runtime)
        try:
            await runtime.run()
        finally:
            restore_signals()

    try:
        asyncio.run(_runner())
    except KeyboardInterrupt:  # pragma: no cover - handled by signal handlers
        typer.secho("Shutdown requested", fg=typer.colors.YELLOW)


@app.command()
def healthcheck() -> None:
    """Check connectivity to Redis mailbox and report status."""
    config = _load_config()

    async def _runner() -> bool:
        return await perform_healthcheck(config)

    healthy = asyncio.run(_runner())
    if not healthy:
        typer.secho("Agent is unhealthy", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho("Agent is healthy", fg=typer.colors.GREEN)


def main() -> None:
    """Entry point for console script."""
    app()


if __name__ == "__main__":
    main()
