# Spec 001 – Core Agent Design

## 1. Design Scope & Goals
- Translate the requirements for the Beast Mailbox Agent into an implementable architecture ready for TDD.
- Define the module boundaries, component responsibilities, and integration points (mailbox, LLM providers, configuration, observability).
- Establish extension points for future capabilities such as conversational context management and additional LLM providers.

## 2. High-Level Architecture

```
┌──────────────────────────────┐
│ CLI Entry (`beast-mailbox-agent`) │
└──────────────┬───────────────┘
               │ loads config
┌──────────────▼───────────────┐
│ AgentRuntime                  │
│ - configuration               │
│ - dependency wiring           │
│ - lifecycle (start/stop)      │
└──────────────┬───────────────┘
               │ owns
┌──────────────▼───────────────┐
│ MailboxProcessor              │
│ - Redis stream loop (async)   │
│ - message parsing/validation  │
│ - dispatch to PromptHandler   │
└──────────────┬───────────────┘
               │ calls
┌──────────────▼─────────────────┐
│ PromptHandler                   │
│ - concurrency gate              │
│ - context retrieval (ext point) │
│ - LLM request construction      │
│ - response formatting           │
└──────────────┬─────────────────┘
               │ delegates
┌──────────────▼───────────────┐   ┌─────────────────────────┐
│ LLMProviderAdapter (interface)│   │ ContextStore (optional) │
│ - `generate(prompt, opts)`    │   │ - Redis-backed storage  │
└──────────────┬───────────────┘   └─────────────────────────┘
               │ implementation
┌──────────────▼───────────────┐
│ OpenAIChatProvider           │
└──────────────────────────────┘
```

### Key Data Flow
1. CLI parses flags/env → builds `AgentConfig`.
2. `AgentRuntime` boots Redis client, LLM adapter, optional context store, and `MailboxProcessor`.
3. `MailboxProcessor` listens via `beast-mailbox-core` async consumer group API, yielding `MailboxMessage`.
4. `PromptHandler` validates payload, fetches (optional) context, invokes LLM adapter respecting concurrency limit.
5. Result (or error) is serialized and sent via `beast-mailbox-core` reply helper; message is acknowledged.

## 3. Data Contracts

### 3.1 Incoming Mailbox Message
```json
{
  "prompt": "Explain the Beast architecture",
  "sender": "service_a",
  "thread_id": "abc123",      // optional, used for context lookup
  "options": {
    "model": "gpt-4o-mini",
    "temperature": 0.2,
    "max_tokens": 300
  },
  "context": {
    "messages": [
      {"role": "user", "content": "..."}  // optional explicit history
    ]
  },
  "metadata": {...}           // arbitrary caller-provided metadata
}
```
- Required fields: `prompt`.
- `sender` and `thread_id` drive correlation + optional context lookup.
- Unrecognized fields are preserved and forwarded in response metadata.

### 3.2 Response Payload
```json
{
  "status": "success",          // or "error"
  "response": {
    "content": "...",           // model output text
    "usage": {
      "prompt_tokens": 123,
      "completion_tokens": 256,
      "total_tokens": 379
    }
  },
  "error": null,                // error details when status = "error"
  "request_id": "<llm-call-id>",
  "message_id": "<mailbox-message-id>",
  "correlation": {
    "sender": "service_a",
    "thread_id": "abc123"
  },
  "metadata": {...}             // echoes metadata/options if provided
}
```
- Error responses include `error.code`, `error.message`, and optional retry hints.
- Responses are posted to mailbox stream specified by caller or default reply stream.

### 3.3 Context Store Keys
- Default key format: `beast:agent:{agent_id}:context:{thread_id}`.
- Values: JSON-serialized array of past messages or compression artefacts as needed.
- TTL configurable via `BEAST_CONTEXT_TTL`.

## 3. Module Breakdown

| Module | Purpose |
|--------|---------|
| `config.py` | Define `AgentConfig`, parse environment/CLI, perform validation. |
| `cli.py` | Click/Typer CLI exposing `run` and `healthcheck` commands. |
| `runtime.py` | `AgentRuntime` orchestrates initialization, startup, graceful shutdown. |
| `mailbox.py` | `MailboxProcessor` encapsulates Redis stream consumption using beast-mailbox-core. |
| `handler.py` | `PromptHandler` handles per-message processing, context retrieval, LLM request/response handling. |
| `providers/base.py` | Abstract base class for LLM providers (`async generate`). |
| `providers/openai.py` | Implementation using OpenAI Chat Completions API via async HTTP client. |
| `context.py` | Define optional `ContextStore` interface and Redis implementation stub. |
| `observability.py` | Logging setup, metrics hooks, correlation utilities. |
| `tests/` | Mirror module structure with unit tests and integration harness using fakes/mocks. |

## 4. Component Responsibilities

### 4.1 `AgentConfig`
- Sources: environment variables, `.env`, CLI flags.
- Validates Redis URL, mailbox identifiers, provider credentials, concurrency limit ≥1, retry/backoff settings.
- Provides derived values (e.g., `redis_dsn`, `llm_options`).

### 4.2 CLI
- `run` command: loads config, instantiates `AgentRuntime`, runs until cancelled (SIGINT/SIGTERM).
- `healthcheck` command: verifies Redis reachability and provider credentials without entering main loop.
- Centralizes exception handling to exit with non-zero code on fatal configuration issues.

### 4.3 `AgentRuntime`
- Builds Redis connection (using `beast-mailbox-core` utilities) and ensures consumer group exists.
- Wires dependencies: `MailboxProcessor`, `PromptHandler`, `LLMProviderAdapter`, optional `ContextStore`.
- Manages lifecycle hooks: startup logs, background task creation, graceful shutdown on cancellation or fatal error.

### 4.4 `MailboxProcessor`
- Async task loop using `XREADGROUP` via beast-mailbox-core.
- Handles pending entries on startup (`claim_pending` helper).
- Enforces poll interval/backoff from config; handles reconnection with retry policy.
- Emits structured logs with message metadata.
- On receiving message, delegates to `PromptHandler.process_message`.

### 4.5 `PromptHandler`
- Validates payload schema and extracts prompt + metadata.
- Applies concurrency semaphore (asyncio) to cap simultaneous LLM requests.
- Retrieves optional prior context via `ContextStore.load(conversation_key)` when configured; passes to provider.
- Constructs provider request (model, temperature, max tokens, etc.).
- Handles provider responses/errors, including retryable vs fatal classification.
- Builds reply payload with correlation IDs and status; instructs mailbox to send response.
- Records metrics (counts, latency) and logs per message outcome.
- **Design Trade-off:** The MVP avoids depending on orchestration frameworks such as LangChain or LangGraph to keep the runtime thin and the dependency surface minimal. The abstraction boundaries here (provider adapter + context store) are intentionally shaped so a future iteration can wrap `PromptHandler` inside a LangGraph/chain-based flow—either in this codebase or as an external orchestration layer—without reworking mailbox integration.

### 4.6 LLM Provider Abstraction
- Base interface: `async def generate(self, prompt: PromptInput, options: PromptOptions) -> PromptResult`.
- `PromptInput` includes prompt text, optional context, metadata.
- `PromptResult` captures completion text, usage stats, provider raw data.
- `OpenAIChatProvider` uses async HTTP client (e.g., `httpx.AsyncClient`) for portability; respects timeout/retry policy.
- Provider-specific errors mapped to domain exceptions (`RetryableProviderError`, `FatalProviderError`).

### 4.7 ContextStore (Extension Point)
- Interface with methods `load(conversation_key)`, `save(conversation_key, context, ttl=None)`, `clear(conversation_key)`.
- Default implementation: no-op (stateless).
- Optional Redis-backed implementation using hashed keys (e.g., `beast:context:{agent_id}:{thread_id}`) to store serialized history with TTL.
- Hook registration via config flag; ensures future conversational features plug in without modifying core flow.

### 4.8 Observability
- Structured logging using `structlog` or standard logging with JSON formatter.
- Correlation IDs: reuse mailbox message ID + sender to tag logs.
- Metrics: simple counter/timer interface (initially log-based) with ability to swap in Prometheus exporter later.
- Error reporting integrates with retry logic to avoid log spam.

## 5. Concurrency & Error Handling

- Use `asyncio` event loop; `MailboxProcessor` runs as long-lived async task.
- Concurrency controlled via `asyncio.Semaphore` in `PromptHandler`; default limit 1, configurable.
- Retries for transient provider errors use exponential backoff with jitter; rely on `tenacity` or custom helper.
- Redis connectivity failures trigger backoff and health logging; fatal config issue leads to runtime shutdown.
- On unhandled exception in `PromptHandler`, message is not acknowledged and is requeued/pending for later retry.
- Provide explicit dead-letter handling hook (dismiss or log) for repeated failures (e.g., after N retries).

## 6. Configuration Surface

| Env Var / CLI Flag | Description | Default |
|--------------------|-------------|---------|
| `BEAST_AGENT_ID` | Agent identifier for mailbox | required |
| `BEAST_REDIS_URL` | Redis connection string | required |
| `BEAST_MAILBOX_STREAM` | Input stream name | `beast:mailbox:{agent_id}:in` |
| `BEAST_MAILBOX_GROUP` | Consumer group name | `agent:{agent_id}` |
| `BEAST_REPLY_STREAM` | Output stream name | derived from sender |
| `BEAST_LLM_PROVIDER` | Provider key (`openai`) | `openai` |
| `BEAST_OPENAI_API_KEY` | Credential for OpenAI | required for provider |
| `BEAST_MODEL_NAME` | Model identifier | `gpt-4o-mini` (configurable) |
| `BEAST_MAX_TOKENS` | Max tokens per reply | 512 |
| `BEAST_TEMPERATURE` | Sampling temperature | 0.2 |
| `BEAST_CONCURRENCY` | Max concurrent prompts | 1 |
| `BEAST_RETRY_MAX` | Provider retry attempts | 3 |
| `BEAST_RETRY_BACKOFF_BASE` | Backoff base seconds | 1.0 |
| `BEAST_CONTEXT_ENABLED` | Enable Redis context store | false |
| `BEAST_CONTEXT_TTL` | Seconds to retain context | 900 |
| `BEAST_LOG_LEVEL` | Logging verbosity | `INFO` |

Configuration parsing consolidates env + CLI overrides, with `.env` support via `python-dotenv`.

## 7. Testing Strategy

- **Unit Tests**
  - `AgentConfig` validation with good/bad inputs.
  - `MailboxProcessor` loop using fake mailbox client to verify pending claim, ack behaviour.
  - `PromptHandler` concurrency logic and payload validation; use stubbed provider/context store.
  - Provider adapter error mapping (retryable vs fatal).

- **Integration Tests**
  - Async test harness using `aioredis` fixture or Redis test container (if allowed); otherwise mock beast-mailbox-core.
  - End-to-end flow: send prompt message → stub provider returns completion → response message emitted.
  - Healthcheck command verifying connection attempts.

- **Contract Tests**
  - Ensure response payload schema matches expectation defined by beast-mailbox-core consumers.
  - Validate log/metric emission structure (can assert key fields).

Coverage tooling: pytest asyncio mode auto, coverage enforced ≥85 %.

## 8. Observability & Ops Considerations

- Provide `--log-format json` option to align with centralized logging.
- Expose heartbeat log every N seconds to signal liveness.
- Document how to integrate metrics with external collectors when available.

## 9. Extensibility & Future Work Alignment

- Provider abstraction supports registering new adapters (Anthropic, Azure) via entry points or config mapping.
- Context store interface allows promoting Redis-backed conversational memory to first-class feature.
- Scheduler/gateway features can wrap `PromptHandler` without modifying mailbox loop.
- CLI can be extended with subcommands (`replay`, `inspect`) once requirements land.

## 10. Implementation Plan (Next Steps)

1. Implement `AgentConfig` + CLI scaffolding with validation tests.
2. Build `AgentRuntime` and `MailboxProcessor` skeleton wired to fake provider for initial loop tests.
3. Implement `PromptHandler` with concurrency semaphore and provider integration (mocked).
4. Implement OpenAI provider adapter with HTTP client abstraction and retry handling.
5. Add optional Redis `ContextStore` stub and configuration hook.
6. Flesh out observability utilities and ensure structured logs.
7. Write integration tests verifying end-to-end message flow with stub provider, hitting coverage targets.

## 11. Open Questions

- Which specific logging library should be standard (stdlib logging vs structlog)?
- Do we need to handle large payload chunking or streaming for responses in MVP?
- Should retries for mailbox acknowledgment be configurable separately from provider retries?
