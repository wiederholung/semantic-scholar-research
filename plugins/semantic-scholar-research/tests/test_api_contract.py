from __future__ import annotations

from typing import Any

import pytest

from semantic_scholar_agent.cli import build_parser, execute
from semantic_scholar_agent.client import RequestStats
from semantic_scholar_agent.normalize import EDGE_FIELDS, PAPER_FIELDS


class ContractClient:
    def __init__(self) -> None:
        self.stats = RequestStats()
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def _record(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append((method, path, kwargs))
        if path == "/paper/batch":
            return []
        if path.startswith("/papers/"):
            return {"recommendedPapers": []}
        return {"data": []}

    def graph_get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._record("GET", path, params=params or {})

    def graph_post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        return self._record("POST", path, params=params or {}, json_body=json_body)

    def recommendations_get(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> Any:
        return self._record("GET", path, params=params or {})

    def recommendations_post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        return self._record("POST", path, params=params or {}, json_body=json_body)


@pytest.mark.parametrize(
    ("argv", "expected_path", "expected_fields"),
    [
        (["search", "--query", "agents"], "/paper/search", PAPER_FIELDS),
        (["bib", "--paper-id", "a" * 40], "/paper/batch", PAPER_FIELDS),
        (
            ["citations", "--paper-id", "a" * 40],
            f"/paper/{'a' * 40}/citations",
            EDGE_FIELDS,
        ),
        (
            ["references", "--paper-id", "a" * 40],
            f"/paper/{'a' * 40}/references",
            EDGE_FIELDS,
        ),
    ],
)
def test_graph_commands_use_documented_routes_and_fields(
    argv: list[str], expected_path: str, expected_fields: str
) -> None:
    client = ContractClient()
    execute(build_parser().parse_args(argv), client)
    assert client.calls[0][1] == expected_path
    assert client.calls[0][2]["params"]["fields"] == expected_fields


def test_snippets_use_the_dedicated_search_route() -> None:
    client = ContractClient()
    execute(build_parser().parse_args(["snippets", "--query", "evidence"]), client)
    assert client.calls == [
        ("GET", "/snippet/search", {"params": {"query": "evidence", "limit": 20}})
    ]
