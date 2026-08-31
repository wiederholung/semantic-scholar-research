from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from semantic_scholar_agent.cli import build_parser, execute, main
from semantic_scholar_agent.client import RequestStats
from semantic_scholar_agent.errors import ValidationError


class RoutingClient:
    def __init__(self, handler: Callable[[str, str, dict[str, Any]], Any]) -> None:
        self.handler = handler
        self.stats = RequestStats()
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.closed = False

    def _call(self, method: str, path: str, kwargs: dict[str, Any]) -> Any:
        self.stats.api_requests += 1
        self.calls.append((method, path, kwargs))
        return self.handler(method, path, kwargs)

    def graph_get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._call("GRAPH_GET", path, {"params": params or {}})

    def graph_post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        return self._call(
            "GRAPH_POST", path, {"params": params or {}, "json_body": json_body}
        )

    def recommendations_get(
        self, path: str, *, params: dict[str, Any] | None = None
    ) -> Any:
        return self._call("RECOMMEND_GET", path, {"params": params or {}})

    def recommendations_post(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        return self._call(
            "RECOMMEND_POST", path, {"params": params or {}, "json_body": json_body}
        )

    def close(self) -> None:
        self.closed = True


def test_search_prints_one_json_object_and_never_prints_key(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    paper_record: dict[str, Any],
) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-secret-never-print")
    client = RoutingClient(
        lambda _method, _path, _kwargs: {
            "total": 1,
            "offset": 0,
            "data": [paper_record],
        }
    )

    exit_code = main(
        ["search", "--query", "test paper", "--limit", "1"],
        client_factory=lambda _key, _rate: client,
    )

    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert exit_code == 0
    assert stdout.count("\n") == 1
    assert payload["status"] == "ok"
    assert payload["result"]["papers"][0]["bibtex"].startswith("@inproceedings")
    assert payload["meta"]["authenticated"] is True
    assert "test-secret-never-print" not in stdout
    assert client.closed is True


def test_project_dotenv_is_loaded_without_overriding_process_environment(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND", raising=False)
    (tmp_path / ".env").write_text(
        "SEMANTIC_SCHOLAR_API_KEY=project-test-secret\n"
        "SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND=25\n",
        encoding="utf-8",
    )
    observed: dict[str, object] = {}
    client = RoutingClient(lambda _method, _path, _kwargs: {"data": []})

    def client_factory(key: str | None, rate: float) -> RoutingClient:
        observed.update(key=key, rate=rate)
        return client

    assert main(["search", "--query", "test"], client_factory=client_factory) == 0
    stdout = capsys.readouterr().out
    assert observed == {"key": "project-test-secret", "rate": 25.0}
    assert "project-test-secret" not in stdout


def test_stdout_is_ascii_safe_and_json_restores_unicode(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    paper_record: dict[str, Any],
) -> None:
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    unicode_record = {**paper_record, "title": "Theory of Mind \u2013 多模态"}
    client = RoutingClient(
        lambda _method, _path, _kwargs: {"total": 1, "data": [unicode_record]}
    )
    assert (
        main(
            ["search", "--query", "多模态"],
            client_factory=lambda _key, _rate: client,
        )
        == 0
    )
    stdout = capsys.readouterr().out
    stdout.encode("ascii")
    payload = json.loads(stdout)
    assert payload["result"]["papers"][0]["title"] == "Theory of Mind \u2013 多模态"


def test_resolve_title_requires_selection(
    paper_record: dict[str, Any],
    second_id: str,
) -> None:
    alternative = {
        **paper_record,
        "paperId": second_id,
        "title": "A Test Paper Extended",
    }

    def handler(_method: str, path: str, _kwargs: dict[str, Any]) -> Any:
        if path == "/paper/search/match":
            return {"data": [{**paper_record, "matchScore": 92.3}]}
        if path == "/paper/search":
            return {"data": [paper_record, alternative]}
        raise AssertionError(path)

    client = RoutingClient(handler)
    args = build_parser().parse_args(["resolve", "--query", "A Test Paper"])
    result = execute(args, client)
    assert result.result["selection_required"] is True
    assert result.result["title_match"]["paper_id"] == paper_record["paperId"]
    assert [paper["paper_id"] for paper in result.result["alternatives"]] == [second_id]


def test_resolve_doi_url_uses_direct_lookup(paper_record: dict[str, Any]) -> None:
    client = RoutingClient(lambda _method, _path, _kwargs: paper_record)
    args = build_parser().parse_args(
        ["resolve", "--query", "HTTPS://DOI.ORG/10.1000/Example"]
    )
    result = execute(args, client)
    assert result.result["selection_required"] is False
    assert client.calls[0][1] == "/paper/DOI%3A10.1000%2FExample"


def test_single_recommend_defaults_to_all_cs(
    canonical_id: str, paper_record: dict[str, Any]
) -> None:
    client = RoutingClient(
        lambda _method, _path, _kwargs: {"recommendedPapers": [paper_record]}
    )
    args = build_parser().parse_args(["recommend", "--positive-id", canonical_id])
    result = execute(args, client)
    assert result.result["mode"] == "single"
    assert result.result["pool"] == "all-cs"
    method, path, kwargs = client.calls[0]
    assert method == "RECOMMEND_GET"
    assert path.endswith(canonical_id)
    assert kwargs["params"]["from"] == "all-cs"


def test_multi_recommend_rejects_pool_before_request(
    canonical_id: str, second_id: str
) -> None:
    client = RoutingClient(lambda *_: pytest.fail("API must not be called"))
    args = build_parser().parse_args(
        [
            "recommend",
            "--positive-id",
            canonical_id,
            "--positive-id",
            second_id,
            "--pool",
            "recent",
        ]
    )
    with pytest.raises(ValidationError):
        execute(args, client)
    assert client.calls == []


def test_bib_preserves_official_entry_and_refuses_overwrite(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    canonical_id: str,
    paper_record: dict[str, Any],
) -> None:
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "test-key")
    bib_path = tmp_path / "papers.bib"
    client = RoutingClient(lambda _method, _path, _kwargs: [paper_record])
    args = ["bib", "--paper-id", canonical_id, "--bib-output", str(bib_path)]
    assert main(args, client_factory=lambda _key, _rate: client) == 0
    capsys.readouterr()
    expected = paper_record["citationStyles"]["bibtex"].strip() + "\n"
    assert bib_path.read_text(encoding="utf-8") == expected

    second_client = RoutingClient(lambda *_: pytest.fail("API must not be called"))
    assert main(args, client_factory=lambda _key, _rate: second_client) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"]["category"] == "output"
    assert second_client.calls == []


def test_invalid_canonical_id_is_structured_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["bib", "--paper-id", "DOI:10.1/example"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert payload["command"] == "bib"
    assert payload["error"]["category"] == "validation"
