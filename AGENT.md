# AGENT.md - Maintainer Guide for AI Agents

**Repository:** beast-mailbox-agent  
**Current Maintainer:** AI Agent (You)  
**Last Updated:** 2025-10-14  
**Project Status:** Under Development (Alpha)

---

## 🎯 Welcome, AI Maintainer!

You are the primary maintainer of **Beast Mailbox Agent**, an LLM-powered agent that receives and responds to prompts via mailbox. This project is unique: it is being **100% implemented by LLMs using spec-driven development**. This document is your comprehensive guide to building and maintaining this repository.

## 🚧 Current Status: Scaffold Phase

This repository was just created from the beast-mailbox-core template. The structure is in place, but **implementation has not started yet**.

**What exists:**
- ✅ Project structure (src/, tests/, docs/, .spec-workflow/)
- ✅ Build configuration (pyproject.toml)
- ✅ CI/CD workflows (GitHub Actions, SonarCloud)
- ✅ Quality tooling setup
- ✅ This maintainer guide

**What needs to be built:**
- ❌ Core agent implementation
- ❌ LLM integration  
- ❌ Mailbox listener
- ❌ Response handler
- ❌ Tests
- ❌ Documentation

**Where to start:**
1. Create specifications in `.spec-workflow/specs/`
2. Follow spec-driven development pattern
3. Implement based on requirements
4. Write tests first (TDD)
5. Maintain quality standards

---

## Project Overview

### What is Beast Mailbox Agent?

An **LLM-powered agent** that:
1. Listens to a Redis mailbox (via beast-mailbox-core)
2. Receives prompts as messages
3. Processes them using an LLM (OpenAI, Anthropic, etc.)
4. Responds back through the mailbox

**Use Cases:**
- Asynchronous LLM request/response
- Multi-agent communication
- Distributed AI workflows
- Event-driven AI processing

### Architecture Vision

```
┌─────────────────┐
│  Prompt Sender  │
└────────┬────────┘
         │ send_message("agent", {"prompt": "..."})
         ▼
┌─────────────────────────────────┐
│   Redis Mailbox                  │
│   Stream: beast:mailbox:agent:in│
└────────┬────────────────────────┘
         │ agent listens via XREADGROUP
         ▼
┌─────────────────────────────────┐
│   Beast Mailbox Agent           │
│   ┌──────────────────────────┐  │
│   │ 1. Receive message       │  │
│   │ 2. Extract prompt        │  │
│   │ 3. Call LLM API          │  │
│   │ 4. Format response       │  │
│   │ 5. Send back             │  │
│   └──────────────────────────┘  │
└────────┬────────────────────────┘
         │ send_message(original_sender, {"response": "..."})
         ▼
┌─────────────────┐
│  Response Rcvd  │
└─────────────────┘
```

---

## Quality Standards

This project inherits quality standards from **beast-mailbox-core**:

### Non-Negotiable Standards

1. **Zero Defects:** No bugs, vulnerabilities, or critical code smells
2. **High Coverage:** Maintain ≥ 85% code coverage
3. **Documentation Density:** Keep ≥ 40% comment density
4. **Tests ≥ Complexity:** Number of tests should exceed cognitive complexity
5. **Quality Gate:** Must pass SonarCloud Quality Gate
6. **All Tests Pass:** 100% test success rate

### Tools & Integrations

- **GitHub Actions:** CI/CD pipeline (tests + SonarCloud)
- **SonarCloud:** Code quality analysis
- **pytest:** Test framework with async support
- **Coverage:** Code coverage measurement

---

## Spec-Driven Development

This project follows the **spec-workflow-mcp** pattern.

### Specifications Directory

```
.spec-workflow/specs/
  001-core-agent/
    requirements.md
    design.md
  002-llm-integration/
    requirements.md
    design.md
  003-...
```

### Development Workflow

1. **Write Specification**
   - Create requirements.md (what to build, why)
   - Create design.md (how to build it)
   - Get approval (or self-approve for now)

2. **Implement from Spec**
   - Read requirements & design
   - Write tests first (TDD)
   - Implement to pass tests
   - Document thoroughly

3. **Verify Quality**
   - Run tests: `pytest tests/ --cov`
   - Check coverage ≥ 85%
   - Run SonarCloud scan
   - Fix any issues

4. **Release**
   - Update CHANGELOG.md
   - Bump version in pyproject.toml
   - Create git tag
   - Publish to PyPI

---

## Dependencies

### Core Dependencies

- **beast-mailbox-core** - Mailbox communication
- **openai** (or anthropic) - LLM API client
- **redis** - Via beast-mailbox-core

### Dev Dependencies

- **pytest** - Testing framework
- **pytest-asyncio** - Async test support
- **pytest-cov** - Coverage measurement

---

## Getting Started as Maintainer

### First Steps

1. **Read Related Project:**
   - Visit https://github.com/nkllon/beast-mailbox-core
   - Read its AGENT.md
   - Understand mailbox patterns

2. **Create First Specification:**
   - Write `.spec-workflow/specs/001-core-agent/requirements.md`
   - Define what the agent should do
   - Define architecture and interfaces

3. **Set Up Development Environment:**
   ```bash
   cd /path/to/beast-mailbox-agent
   python -m venv venv
   source venv/bin/activate
   pip install -e ".[dev]"
   ```

4. **Write First Test:**
   ```bash
   # Create tests/test_agent.py
   # Write a simple test
   # Run: pytest tests/
   ```

5. **Implement:**
   - Follow TDD (test-first)
   - Follow specs
   - Document everything

---

## Critical Lessons (Inherited from beast-mailbox-core)

### From Sister Project

The beast-mailbox-core project learned these lessons the hard way. **Learn from them:**

1. **Repository is Source of Truth** - Always commit → tag → push before publishing
2. **Tests ≥ Cognitive Complexity** - Maintain at least one test per unit of complexity
3. **Documentation Density Matters** - Aim for 40%+ comment density
4. **Some Code is Intentionally Untestable** - Accept architectural limitations (infinite loops)
5. **Engage with Quality Tools** - Don't just suppress warnings, understand them
6. **AsyncIO CancelledError Must Be Re-Raised** - Except in cleanup handlers
7. **Small, Frequent Releases Build Confidence** - Release early, release often
8. **False CHANGELOG Claims Destroy Trust** - Always verify what you claim
9. **Editable Install for Development** - Use `pip install -e .` for accurate coverage
10. **Quality is a Choice** - Excellence is achievable through systematic pursuit

### For This Project

**Additional considerations:**
- **LLM Rate Limits:** Implement exponential backoff
- **LLM Errors:** Handle gracefully, don't crash
- **Async Patterns:** Use asyncio properly
- **Message Format:** Define clear schemas
- **Error Messages:** Clear, actionable, logged

---

## Troubleshooting

### Common Issues

**Issue:** Tests not finding modules

**Solution:**
```bash
pip install -e ".[dev]"  # Editable install
```

**Issue:** Async tests hanging

**Solution:**
```python
# In pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"  # Critical!
```

**Issue:** SonarCloud failing

**Solution:**
- Check `.github/workflows/sonarcloud.yml`
- Ensure `SONAR_TOKEN` secret is set
- Verify using correct action: `sonarcloud-github-action@master`

---

## Quick Reference

### Essential Commands

```bash
# Development
pip install -e ".[dev]"           # Install for development
pytest tests/                     # Run all tests
pytest tests/ --cov              # Run with coverage
python -m build                  # Build package

# Quality
pytest tests/ --cov-report=html  # Generate coverage HTML
# Visit SonarCloud for quality metrics

# Running the agent
beast-agent my-agent-id --redis-host localhost
```

### Key Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, dependencies |
| `README.md` | User documentation |
| `AGENT.md` | This file - maintainer guide |
| `.spec-workflow/specs/` | Specifications |
| `src/beast_mailbox_agent/` | Source code |
| `tests/` | Test suite |

---

## Maintenance Philosophy

### Core Principles

1. **Spec-First:** Write specification before code
2. **Test-First:** Write tests before implementation
3. **Document-First:** Write docstrings as you code
4. **Quality-First:** Never compromise on standards
5. **User-First:** Build what users need

### Decision Framework

**Before implementing anything, ask:**
1. Is there a spec for this?
2. Are there tests for this?
3. Is this documented?
4. Does this meet quality standards?
5. Does this solve a real problem?

---

## Success Metrics

You're succeeding if:
- ✅ All specs have implementations
- ✅ All code has tests (≥85% coverage)
- ✅ All functions have docstrings (≥40% density)
- ✅ Quality Gate passes (SonarCloud)
- ✅ Users can install and use it
- ✅ Agent responds to prompts reliably

---

## Next Steps for You

**Immediate (Day 1):**
1. Create first specification in `.spec-workflow/specs/001-core-agent/`
2. Define requirements: What should this agent do?
3. Define design: How will it work?

**Short-term (Week 1):**
1. Implement core agent class
2. Integrate with beast-mailbox-core
3. Add LLM integration
4. Write comprehensive tests
5. Achieve ≥85% coverage

**Long-term (Month 1):**
1. Multiple LLM providers supported
2. Robust error handling
3. Production-ready quality
4. Published to PyPI
5. Documentation complete

---

## Welcome Aboard! 🚀

You're starting from a clean slate with a proven structure. This project will demonstrate spec-driven development from the ground up. Every decision, every line of code, every test will be intentional and documented.

**Remember:**
- Specs come first
- Tests come second  
- Implementation comes third
- Documentation is continuous
- Quality is non-negotiable

Good luck building something excellent! 📊✨

---

**Last Updated:** 2025-10-14  
**Maintained By:** AI Agent (You)  
**Document Version:** 1.0.0

**Questions?** Read beast-mailbox-core's AGENT.md and LESSONS_LEARNED for detailed guidance.
