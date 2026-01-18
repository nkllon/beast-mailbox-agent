"""Tests for the OpenAI provider adapter."""

from types import SimpleNamespace

import httpx
import pytest

from openai import APIError, RateLimitError

from beast_mailbox_agent.providers.base import PromptRequest, ProviderError
from beast_mailbox_agent.providers.openai import OpenAIChatProvider


class _FakeCompletions:
    def __init__(self, response):
        self._response = response
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.chat = SimpleNamespace(completions=_FakeCompletions(response))
        self.closed = False
        self.timeout_options = None

    def with_options(self, **kwargs):
        self.timeout_options = kwargs
        return self

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_openai_provider_success(monkeypatch):
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="result text"))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        model="test-model",
        id="resp-1",
    )
    fake_client = _FakeClient(fake_response)

    monkeypatch.setattr(
        "beast_mailbox_agent.providers.openai.AsyncOpenAI",
        lambda *args, **kwargs: fake_client,
    )

    provider = OpenAIChatProvider(
        api_key="key",
        default_model="default-model",
        timeout=20.0,
        default_options={"temperature": 0.1},
    )

    request = PromptRequest(
        prompt="Tell me something",
        options={"timeout": 5.0, "max_tokens": 100},
        metadata={},
        context={"messages": [{"role": "system", "content": "Hi"}]},
    )

    response = await provider.generate(request)

    assert response.content == "result text"
    assert response.model == "test-model"
    assert response.request_id == "resp-1"
    assert response.usage["total_tokens"] == 15
    assert fake_client.timeout_options == {"timeout": 5.0}
    assert fake_client.chat.completions.calls[0]["model"] == "default-model"
    await provider.aclose()
    assert fake_client.closed is True


class _ErrorClient:
    def __init__(self, error_factory):
        self._error_factory = error_factory
        self.chat = SimpleNamespace(completions=self)

    def with_options(self, **kwargs):
        return self

    def close(self):
        pass

    async def create(self, **kwargs):
        raise self._error_factory()


@pytest.mark.asyncio
async def test_openai_provider_raises_retryable(monkeypatch):
    def _error():
        response = httpx.Response(429, request=httpx.Request("POST", "https://example.com"))
        return RateLimitError("throttle", response=response, body=None)

    client = _ErrorClient(_error)
    monkeypatch.setattr(
        "beast_mailbox_agent.providers.openai.AsyncOpenAI",
        lambda *args, **kwargs: client,
    )

    provider = OpenAIChatProvider(api_key="key", default_model="model", timeout=1.0)

    with pytest.raises(ProviderError) as exc:
        await provider.generate(PromptRequest(prompt="hi", options={}, metadata={}))

    assert exc.value.retryable is True


@pytest.mark.asyncio
async def test_openai_provider_wraps_api_error(monkeypatch):
    def _error():
        err = APIError("fail", httpx.Request("POST", "https://example.com"), body=None)
        err.code = "server_error"
        err.status = 500
        return err

    client = _ErrorClient(_error)
    monkeypatch.setattr(
        "beast_mailbox_agent.providers.openai.AsyncOpenAI",
        lambda *args, **kwargs: client,
    )

    provider = OpenAIChatProvider(api_key="key", default_model="model", timeout=1.0)

    with pytest.raises(ProviderError) as exc:
        await provider.generate(PromptRequest(prompt="boom", options={}, metadata={}))

    assert exc.value.code == "server_error"
    assert exc.value.details["status_code"] == 500
