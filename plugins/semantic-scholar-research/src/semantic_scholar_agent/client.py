from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime
from typing import Any, Self

import httpx

from .errors import S2APIError, ValidationError

GRAPH_BASE_URL = "https://api.semanticscholar.org/graph/v1"
RECOMMENDATIONS_BASE_URL = "https://api.semanticscholar.org/recommendations/v1"
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


@dataclass(slots=True)
class RequestStats:
    api_requests: int = 0
    retries: int = 0
    rate_limited: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_requests": self.api_requests,
            "retries": self.retries,
            "rate_limited": self.rate_limited,
        }


def _safe_api_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return f"Semantic Scholar returned HTTP {response.status_code}"
    if isinstance(payload, dict):
        for key in ("error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:500]
    return f"Semantic Scholar returned HTTP {response.status_code}"


def _retry_after_seconds(value: str | None, now: Callable[[], float]) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0.0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, retry_at.timestamp() - now())
    except (TypeError, ValueError, OverflowError):
        return None


class S2Client:
    """Small synchronous client with conservative throttling and structured failures."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        requests_per_second: float = 1.0,
        max_attempts: int = 4,
        max_retry_after: float = 30.0,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        wall_time: Callable[[], float] = time.time,
    ) -> None:
        if requests_per_second <= 0:
            raise ValidationError("requests_per_second must be greater than zero")
        if max_attempts < 1:
            raise ValidationError("max_attempts must be at least one")
        self._api_key = api_key.strip() if api_key and api_key.strip() else None
        self._interval = 1.0 / requests_per_second
        self._max_attempts = max_attempts
        self._max_retry_after = max_retry_after
        self._sleep = sleep
        self._monotonic = monotonic
        self._wall_time = wall_time
        self._last_request_started: float | None = None
        self._owns_client = http_client is None
        headers = {
            "Accept": "application/json",
            "User-Agent": "tom-mllm-semantic-scholar-agent/0.1",
        }
        if self._api_key:
            headers["x-api-key"] = self._api_key
        self._client = http_client or httpx.Client(timeout=timeout, headers=headers)
        if http_client is not None:
            self._client.headers.update(headers)
        self.stats = RequestStats()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _throttle(self) -> None:
        if self._last_request_started is not None:
            wait = self._interval - (self._monotonic() - self._last_request_started)
            if wait > 0:
                self._sleep(wait)
        self._last_request_started = self._monotonic()

    def request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        base_url: str = GRAPH_BASE_URL,
    ) -> Any:
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        for attempt in range(self._max_attempts):
            self._throttle()
            self.stats.api_requests += 1
            try:
                response = self._client.request(
                    method, url, params=params, json=json_body
                )
            except httpx.RequestError as exc:
                if attempt + 1 < self._max_attempts:
                    self.stats.retries += 1
                    self._sleep(min(2**attempt, self._max_retry_after))
                    continue
                raise S2APIError(
                    "Could not reach Semantic Scholar after retries",
                    category="network",
                ) from exc

            if response.status_code in RETRYABLE_STATUS_CODES:
                self.stats.rate_limited = (
                    self.stats.rate_limited or response.status_code == 429
                )
                retry_after = _retry_after_seconds(
                    response.headers.get("Retry-After"), self._wall_time
                )
                delay = retry_after if retry_after is not None else float(2**attempt)
                if attempt + 1 < self._max_attempts and delay <= self._max_retry_after:
                    self.stats.retries += 1
                    self._sleep(delay)
                    continue
                category = "rate_limit" if response.status_code == 429 else "upstream"
                raise S2APIError(
                    _safe_api_message(response),
                    category=category,
                    status_code=response.status_code,
                    retry_after=retry_after,
                )

            if response.status_code >= 400:
                if response.status_code in {401, 403}:
                    category = "auth"
                elif response.status_code == 404:
                    category = "not_found"
                elif response.status_code == 400:
                    category = "validation"
                else:
                    category = "api"
                raise S2APIError(
                    _safe_api_message(response),
                    category=category,
                    status_code=response.status_code,
                )

            try:
                return response.json()
            except ValueError as exc:
                raise S2APIError(
                    "Semantic Scholar returned a non-JSON response",
                    category="protocol",
                    status_code=response.status_code,
                ) from exc
        raise AssertionError("retry loop exhausted without returning or raising")

    def graph_get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self.request_json("GET", path, params=params)

    def graph_post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        return self.request_json("POST", path, params=params, json_body=json_body)

    def recommendations_get(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> Any:
        return self.request_json(
            "GET", path, params=params, base_url=RECOMMENDATIONS_BASE_URL
        )

    def recommendations_post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        return self.request_json(
            "POST",
            path,
            params=params,
            json_body=json_body,
            base_url=RECOMMENDATIONS_BASE_URL,
        )
