# Spec 001 – Core Agent Requirements

## 1. Purpose
- Define the minimum viable behaviour for the Beast Mailbox Agent so that it can receive prompts from a Redis-backed mailbox, invoke an LLM, and post responses back to the originator.
- Establish non-functional expectations (observability, resilience, quality) for the alpha release.

## 2. Problem Statement
- Consumers of `beast-mailbox-core` need an off-the-shelf agent that can answer prompts asynchronously using an LLM provider.
- No reference implementation exists today; teams roll their own glue code, leading to duplicated effort, inconsistent quality, and poor observability.
- We must provide a reliable, configurable agent that can be deployed headlessly and managed via mailbox commands.

## 3. Goals
- Ship an installable Python package exposing a CLI entrypoint to run the agent.
- Support mailbox I/O via `beast-mailbox-core` primitives: join mailbox group, read prompts, send reply messages.
- Support at least one LLM provider (OpenAI-compatible) with a pluggable abstraction for future providers.
- Provide configuration via environment variables and optional `.env` file; allow per-message overrides when supported.
- Deliver instrumentation hooks (structured logs + basic metrics) for message lifecycle and LLM call outcomes.
- Meet repository quality bars: ≥85 % coverage, ≥40 % documentation density, zero critical sonar issues.

## 4. Non-Goals
- Multi-tenant / multi-agent orchestration beyond a single agent process.
- Provider-specific advanced features (e.g., tool calling, function calling) beyond simple prompt→completion flows.
- Rich UI or dashboard; CLI output and logs are sufficient.
- Persistence of conversation history beyond what the mailbox provides.

## 5. Stakeholders & Users
- **Agent Operators:** DevOps or platform engineers running the agent service.
- **Prompt Producers:** Services or agents sending prompts into the mailbox.
- **Maintainers:** Developers extending the agent with new providers or behaviours.

## 6. Functional Requirements
1. **Startup & Configuration**
   - The CLI (`beast-mailbox-agent run` or similar) must load configuration from env vars and CLI flags.
   - Required config: Redis connection, mailbox stream/group names, agent identifier, provider credentials.
   - Optional config: poll interval/backoff, max concurrent LLM requests, logging verbosity, retry policy.
   - Validate configuration on startup; fail fast with actionable errors.
2. **Mailbox Integration**
   - Join mailbox consumer group and continuously poll for messages addressed to the agent ID.
   - Parse incoming message payloads, expecting `{"prompt": str, ...}`; reject malformed payloads with logged warnings and send error response.
   - Treat each prompt as a stateless request by default; callers may embed prior context explicitly in the payload, and future iterations can layer reusable memory components without breaking this contract.
   - Provide an extension point for optional conversation state storage (e.g., Redis-backed context buffers) so that richer dialog management can be added with minimal changes.
   - Acknowledge processed messages, handle pending entries on startup, and avoid message loss/duplication.
3. **Prompt Processing**
   - For each valid prompt, construct an LLM request using provider adapter abstraction.
   - Leverage asynchronous processing for prompt handling while allowing the initial release to cap in-flight requests via a tunable concurrency limit (default 1).
   - Capture metadata (message ID, sender, timestamps) for logging and tracing.
4. **LLM Invocation**
   - Provide adapter interface with at least an OpenAI-compatible implementation (Chat Completions API).
   - Support configurable model name, temperature, max tokens, and request timeout.
   - Surface provider errors with retryable vs non-retryable distinction; apply retry policy (e.g., exponential backoff) for transient failures.
5. **Response Handling**
   - Format and send response messages back to originating mailbox channel using `beast-mailbox-core` conventions.
   - Include status metadata (success, error reason) and response content.
   - Ensure correlating identifiers (message ID or correlation ID) are preserved for the sender.
6. **Observability & Ops**
   - Emit structured logs for lifecycle events (startup, configuration, message received, LLM request, response sent, errors).
   - Expose metrics hooks (counter/gauge) or at minimum log-friendly metrics for requests, latency, errors.
   - Provide health endpoint or readiness check callable from CLI (e.g., `beast-mailbox-agent healthcheck`) to verify environment.
7. **Error Handling & Recovery**
   - Handle mailbox connectivity issues with retry/backoff and safe shutdown.
   - Protect against provider rate limits by respecting HTTP 429 and `Retry-After`.
   - Guard against unhandled exceptions; agent should continue running unless fatal configuration errors occur.
8. **Development & Testing**
   - Include contract tests for mailbox integration using mocks or local Redis fixture.
   - Provide integration test harness stubbing LLM provider to validate end-to-end prompt→response path.

## 7. Non-Functional Requirements
- **Reliability:** Agent must process messages without unbounded loss; feature toggles to drop or requeue on failure.
- **Performance:** Handle at least 10 concurrent prompts with <5 s latency when LLM responds promptly.
- **Security:** Do not log sensitive tokens or prompt content unless explicitly enabled; support secrets via env vars.
- **Configurability:** All operational parameters configurable without code changes; document defaults.
- **Maintainability:** Follow spec-driven workflow; ensure clear separation between mailbox core, agent logic, and provider adapters.

## 8. Acceptance Criteria
- Repo contains completed requirements and design specs for Spec 001.
- Automated tests cover mailbox polling, LLM adapter behaviour (mocked), and response handling with ≥85 % coverage for new modules.
- CLI entrypoint can be invoked locally with mocked dependencies to process sample prompt and produce response.
- Structured logging visible during sample run with clear correlation IDs.
- Documentation updated: README quickstart section for running the agent and configuring provider.

## 9. Dependencies
- `beast-mailbox-core` library for Redis mailbox abstraction.
- Redis server for local/integration testing (can use container or test fixture).
- LLM provider SDK (OpenAI python client or compatible HTTP client).
- Logging/metrics libraries (standard `logging`, optional `structlog` or similar).

## 10. Open Questions
- Which additional providers should be targeted after OpenAI (Anthropic, Azure OpenAI, etc.)?
- Should we support streaming responses in the first release or defer?
- Do we need built-in prompt sanitization or leave it to callers?
- What is the retention policy for processed mailbox messages?

## 11. Future Work Signals
- Multi-provider routing and per-message provider selection.
- Tool calling / function calling support once core pipeline stabilizes.
- Advanced scheduling (priorities, rate limiting per sender).
- Deployment blueprints (Docker image, Helm chart) for production readiness.
- First-class conversational context management leveraging Redis storage primitives in the Beast mode network.
