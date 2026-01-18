# Beast Mailbox Agent

[![PyPI version](https://img.shields.io/pypi/v/beast-mailbox-agent?label=PyPI&color=blue)](https://pypi.org/project/beast-mailbox-agent/)
[![Python Versions](https://img.shields.io/pypi/pyversions/beast-mailbox-agent.svg)](https://pypi.org/project/beast-mailbox-agent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**LLM agent that receives and responds to prompts via beast-mailbox-core**

## Status

🚧 **Under Development** - This project is being built from scratch using AI-driven spec-driven development.

## Overview

Beast Mailbox Agent is an LLM-powered agent that:
- Listens to a mailbox (via [beast-mailbox-core](https://github.com/nkllon/beast-mailbox-core))
- Receives prompts as messages
- Processes them using an LLM
- Responds back through the mailbox

## Architecture

```
┌─────────────────┐
│  Prompt Sender  │
└────────┬────────┘
         │ (sends message)
         ▼
┌─────────────────────────────────┐
│   Redis Mailbox                  │
│   (beast-mailbox-core)          │
└────────┬────────────────────────┘
         │ (agent listens)
         ▼
┌─────────────────────────────────┐
│   Beast Mailbox Agent           │
│   ┌──────────────────────────┐  │
│   │ 1. Receive prompt        │  │
│   │ 2. Process with LLM      │  │
│   │ 3. Send response         │  │
│   └──────────────────────────┘  │
└─────────────────────────────────┘
```

## Installation

```bash
pip install beast-mailbox-agent
```

## Usage

Set the required environment variables and launch the runtime:

```bash
export BEAST_AGENT_ID=my-agent
export BEAST_REDIS_URL=redis://localhost:6379/0
export BEAST_OPENAI_API_KEY=sk-...

# Run the agent until interrupted
beast-agent run

# Optional: verify connectivity upfront
beast-agent healthcheck
```

Additional options (model, temperature, concurrency, etc.) are configurable via
environment variables documented in `src/beast_mailbox_agent/config.py`.

Secrets such as `BEAST_REDIS_PASSWORD` or provider keys can be stored in
`~/.env`; the agent loads that file automatically on startup.

### Metrics

- `BEAST_METRICS_BACKEND` (`logging` default, `prometheus` supported)
- `BEAST_METRICS_PORT` (optional; when set and backend is `prometheus`, the agent
  starts an HTTP endpoint for Prometheus scraping)

## Development Status

This project follows **spec-driven development**. See [`.spec-workflow/`](.spec-workflow/) for:
- Requirements specifications
- Design documents
- Implementation plans

## For AI Maintainers

**This repository is built 100% by AI agents and maintained by AI agents.**

Start here:
- **📖 [AGENT.md](AGENT.md)** - Comprehensive maintainer guide
- **📁 [.spec-workflow/](.spec-workflow/)** - Specifications and requirements

## Quality Standards

This project maintains the same quality standards as beast-mailbox-core:
- ✅ ≥ 85% test coverage
- ✅ Zero defects (SonarCloud)
- ✅ Comprehensive documentation
- ✅ All tests passing

## License

MIT

---

**Built with ❤️ by AI agents**
