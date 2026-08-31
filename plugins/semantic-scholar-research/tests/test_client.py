from __future__ import annotations

import httpx
import pytest

from semantic_scholar_agent.client import S2Client
from semantic_scholar_agent.errors import S2APIError


def test_client_sends_key_only_in_header_and_returns_json() -> None:
    observed: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["key"] = request.headers.get("x-api-key", "")
        observed["user_agent"] = request.headers.get("user-agent", "")
        return httpx.Response(200, json={"ok": True})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = S2Client(
        api_key="test-secret", requests_per_second=1_000_000, http_client=http_client
    )
    try:
        assert client.graph_get("/paper/search", params={"query": "x"}) == {"ok": True}
    finally:
        http_client.close()
    assert observed["key"] == "test-secret"
    assert "semantic-scholar-agent" in observed["user_agent"]


def test_client_retries_rate_limit_without_exposing_headers() -> None:
    responses = [
        httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "slow down"}),
        httpx.Response(200, json={"data": []}),
    ]
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = S2Client(
        api_key="test-secret",
        requests_per_second=1_000_000,
        http_client=http_client,
        sleep=sleeps.append,
    )
    try:
        assert client.graph_get("/paper/search") == {"data": []}
    finally:
        http_client.close()
    assert client.stats.api_requests == 2
    assert client.stats.retries == 1
    assert client.stats.rate_limited is True
    assert all(delay < 1 for delay in sleeps)


def test_client_refuses_long_retry_after() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, headers={"Retry-After": "120"}, json={"error": "quota"}
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = S2Client(requests_per_second=1_000_000, http_client=http_client)
    try:
        with pytest.raises(S2APIError) as raised:
            client.graph_get("/paper/search")
    finally:
        http_client.close()
    assert raised.value.category == "rate_limit"
    assert raised.value.details["retry_after_seconds"] == 120
    assert client.stats.api_requests == 1
