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

```bash
# Start the agent
beast-agent my-agent-id \
  --redis-host vonnegut \
  --redis-password beastmode2025 \
  --llm-provider openai \
  --llm-model gpt-4
```

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

