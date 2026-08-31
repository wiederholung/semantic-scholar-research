from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from dotenv import load_dotenv

from .client import S2Client
from .errors import AgentError, OutputError, S2APIError, ValidationError
from .normalize import (
    EDGE_FIELDS,
    PAPER_FIELDS,
    RECOMMENDATION_FIELDS,
    normalize_edges,
    normalize_paper,
    normalize_papers,
    normalize_snippets,
)

SCHEMA_VERSION = "1.0"
CANONICAL_PAPER_ID_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
ARXIV_RE = re.compile(
    r"^(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]+/\d{7})(?:v\d+)?$", re.IGNORECASE
)
PREFIXED_ID_RE = re.compile(
    r"^(?:CorpusId|DOI|ARXIV|MAG|ACL|PMID|PMCID|URL):.+$", re.IGNORECASE
)


@dataclass(slots=True)
class CommandResult:
    result: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    bibtex_text: str | None = None


class AgentArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValidationError(message)


def _bounded_int(minimum: int, maximum: int) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("must be an integer") from exc
        if not minimum <= number <= maximum:
            raise argparse.ArgumentTypeError(f"must be between {minimum} and {maximum}")
        return number

    return parse


def _canonical_paper_id(value: str) -> str:
    normalized = value.strip()
    if not CANONICAL_PAPER_ID_RE.fullmatch(normalized):
        raise argparse.ArgumentTypeError(
            "must be a canonical 40-character Semantic Scholar paperId; run resolve first"
        )
    return normalized.lower()


def _add_output_arguments(
    parser: argparse.ArgumentParser, *, bibtex: bool = False
) -> None:
    parser.add_argument("--output", help="Write the JSON envelope to this path")
    if bibtex:
        parser.add_argument(
            "--bib-output", help="Write confirmed Semantic Scholar BibTeX entries"
        )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacement of explicit output files",
    )


def build_parser() -> AgentArgumentParser:
    parser = AgentArgumentParser(prog="s2-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser(
        "search", help="Run a bounded Semantic Scholar relevance search"
    )
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=_bounded_int(1, 100), default=10)
    search.add_argument("--offset", type=_bounded_int(0, 999), default=0)
    search.add_argument("--year")
    search.add_argument("--publication-date-or-year")
    search.add_argument("--publication-type", action="append", default=[])
    search.add_argument("--field-of-study", action="append", default=[])
    search.add_argument("--venue", action="append", default=[])
    search.add_argument("--min-citations", type=_bounded_int(0, 2_147_483_647))
    search.add_argument("--open-access", action="store_true")
    _add_output_arguments(search)

    resolve = subparsers.add_parser(
        "resolve", help="Resolve an identifier or return title candidates"
    )
    resolve.add_argument("--query", required=True)
    resolve.add_argument("--candidate-limit", type=_bounded_int(1, 20), default=5)
    _add_output_arguments(resolve)

    bib = subparsers.add_parser(
        "bib", help="Fetch official BibTeX for confirmed canonical paper IDs"
    )
    bib.add_argument(
        "--paper-id", action="append", type=_canonical_paper_id, required=True
    )
    _add_output_arguments(bib, bibtex=True)

    recommend = subparsers.add_parser(
        "recommend", help="Recommend papers from positive and negative seeds"
    )
    recommend.add_argument(
        "--positive-id", action="append", type=_canonical_paper_id, required=True
    )
    recommend.add_argument(
        "--negative-id", action="append", type=_canonical_paper_id, default=[]
    )
    recommend.add_argument("--pool", choices=("all-cs", "recent"))
    recommend.add_argument("--limit", type=_bounded_int(1, 500), default=30)
    _add_output_arguments(recommend)

    citations = subparsers.add_parser(
        "citations", help="Fetch papers that cite a confirmed paper"
    )
    citations.add_argument("--paper-id", type=_canonical_paper_id, required=True)
    citations.add_argument("--limit", type=_bounded_int(1, 1000), default=50)
    citations.add_argument("--offset", type=_bounded_int(0, 9_999), default=0)
    citations.add_argument("--publication-date-or-year")
    _add_output_arguments(citations)

    references = subparsers.add_parser(
        "references", help="Fetch papers referenced by a confirmed paper"
    )
    references.add_argument("--paper-id", type=_canonical_paper_id, required=True)
    references.add_argument("--limit", type=_bounded_int(1, 1000), default=50)
    references.add_argument("--offset", type=_bounded_int(0, 9_999), default=0)
    _add_output_arguments(references)

    snippets = subparsers.add_parser(
        "snippets", help="Search text snippets, optionally within selected papers"
    )
    snippets.add_argument("--query", required=True)
    snippets.add_argument(
        "--paper-id", action="append", type=_canonical_paper_id, default=[]
    )
    snippets.add_argument("--limit", type=_bounded_int(1, 1000), default=20)
    snippets.add_argument("--year")
    _add_output_arguments(snippets)
    return parser


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_environment() -> tuple[str | None, float]:
    # Process environment wins, followed by the active project and finally the
    # plugin's own development checkout. Installed plugin directories are
    # ephemeral, so users should not have to place credentials there.
    environment_files = (Path.cwd() / ".env", _project_root() / ".env")
    for environment_file in dict.fromkeys(environment_files):
        load_dotenv(environment_file, override=False)
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    raw_rate = os.getenv("SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND", "1")
    try:
        requests_per_second = float(raw_rate)
    except ValueError as exc:
        raise ValidationError(
            "SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND must be numeric",
            field="SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND",
        ) from exc
    if requests_per_second <= 0:
        raise ValidationError(
            "SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND must be greater than zero",
            field="SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND",
        )
    return api_key, requests_per_second


def _require_query(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValidationError("query cannot be empty", field="query")
    return normalized


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _direct_identifier(query: str) -> str | None:
    value = query.strip()
    lowered = value.lower()
    if lowered.startswith(("https://doi.org/", "http://doi.org/")):
        return f"DOI:{urlparse(value).path.lstrip('/')}"
    if DOI_RE.fullmatch(value):
        return f"DOI:{value}"
    if ARXIV_RE.fullmatch(value):
        return f"ARXIV:{value}"
    if CANONICAL_PAPER_ID_RE.fullmatch(value) or PREFIXED_ID_RE.fullmatch(value):
        return value
    if lowered.startswith(("https://arxiv.org/abs/", "http://arxiv.org/abs/")):
        return f"ARXIV:{urlparse(value).path.removeprefix('/abs/')}"
    if lowered.startswith("https://www.semanticscholar.org/paper/"):
        candidate = urlparse(value).path.rstrip("/").split("/")[-1]
        if CANONICAL_PAPER_ID_RE.fullmatch(candidate):
            return candidate
    if lowered.startswith(("https://", "http://")):
        return f"URL:{value}"
    return None


def _search(args: argparse.Namespace, client: S2Client) -> CommandResult:
    query = _require_query(args.query)
    params: dict[str, Any] = {
        "query": query,
        "fields": PAPER_FIELDS,
        "limit": args.limit,
        "offset": args.offset,
    }
    if args.year:
        params["year"] = args.year
    if args.publication_date_or_year:
        params["publicationDateOrYear"] = args.publication_date_or_year
    if args.publication_type:
        params["publicationTypes"] = ",".join(_dedupe(args.publication_type))
    if args.field_of_study:
        params["fieldsOfStudy"] = ",".join(_dedupe(args.field_of_study))
    if args.venue:
        params["venue"] = ",".join(_dedupe(args.venue))
    if args.min_citations is not None:
        params["minCitationCount"] = args.min_citations
    if args.open_access:
        params["openAccessPdf"] = ""
    response = client.graph_get("/paper/search", params=params)
    papers = normalize_papers(
        response.get("data") if isinstance(response, dict) else None
    )
    warnings: list[str] = []
    missing_bibtex = sum(1 for paper in papers if not paper.get("bibtex"))
    if missing_bibtex:
        warnings.append(
            f"{missing_bibtex} candidate(s) did not include Semantic Scholar BibTeX"
        )
    if not papers:
        warnings.append("Search returned no papers")
    return CommandResult(
        result={
            "query": query,
            "total": response.get("total") if isinstance(response, dict) else None,
            "offset": response.get("offset")
            if isinstance(response, dict)
            else args.offset,
            "next": response.get("next") if isinstance(response, dict) else None,
            "papers": papers,
        },
        warnings=warnings,
    )


def _resolve(args: argparse.Namespace, client: S2Client) -> CommandResult:
    query = _require_query(args.query)
    identifier = _direct_identifier(query)
    if identifier is not None:
        response = client.graph_get(
            f"/paper/{quote(identifier, safe='')}",
            params={"fields": PAPER_FIELDS},
        )
        paper = normalize_paper(response)
        if paper is None:
            raise S2APIError(
                "Resolved response did not contain a paperId", category="protocol"
            )
        return CommandResult(
            result={
                "query": query,
                "query_kind": "identifier",
                "selection_required": False,
                "paper": paper,
                "alternatives": [],
            }
        )

    warnings: list[str] = []
    title_match: dict[str, Any] | None = None
    try:
        match_response = client.graph_get(
            "/paper/search/match",
            params={"query": query, "fields": PAPER_FIELDS},
        )
        match_data = (
            match_response.get("data") if isinstance(match_response, dict) else None
        )
        if isinstance(match_data, list) and match_data:
            title_match = normalize_paper(match_data[0])
    except S2APIError as exc:
        if exc.category != "not_found":
            raise
        warnings.append("Semantic Scholar title match returned no paper")

    search_response = client.graph_get(
        "/paper/search",
        params={
            "query": query,
            "fields": PAPER_FIELDS,
            "limit": args.candidate_limit,
            "offset": 0,
        },
    )
    candidates = normalize_papers(
        search_response.get("data") if isinstance(search_response, dict) else None
    )
    if title_match is not None:
        candidates = [
            paper
            for paper in candidates
            if paper["paper_id"] != title_match["paper_id"]
        ]
    if title_match is None and not candidates:
        warnings.append("No resolution candidates were found")
    return CommandResult(
        result={
            "query": query,
            "query_kind": "title",
            "selection_required": True,
            "title_match": title_match,
            "alternatives": candidates,
        },
        warnings=warnings,
    )


def _bib(args: argparse.Namespace, client: S2Client) -> CommandResult:
    paper_ids = _dedupe(args.paper_id)
    response = client.graph_post(
        "/paper/batch",
        params={"fields": PAPER_FIELDS},
        json_body={"ids": paper_ids},
    )
    returned = normalize_papers(response)
    by_id = {paper["paper_id"]: paper for paper in returned}
    papers = [by_id[paper_id] for paper_id in paper_ids if paper_id in by_id]
    missing_ids = [paper_id for paper_id in paper_ids if paper_id not in by_id]
    missing_bibtex_ids = [
        paper["paper_id"] for paper in papers if not paper.get("bibtex")
    ]
    warnings: list[str] = []
    if missing_ids:
        warnings.append(f"{len(missing_ids)} requested paperId(s) were not returned")
    if missing_bibtex_ids:
        warnings.append(
            f"{len(missing_bibtex_ids)} paper(s) did not include Semantic Scholar BibTeX"
        )
    entries = [paper["bibtex"].strip() for paper in papers if paper.get("bibtex")]
    duplicate_keys = _duplicate_bibtex_keys(entries)
    if duplicate_keys:
        warnings.append(
            "Duplicate BibTeX citation key(s): " + ", ".join(duplicate_keys)
        )
    bibtex_text = "\n\n".join(entries) + ("\n" if entries else "")
    return CommandResult(
        result={
            "requested_paper_ids": paper_ids,
            "papers": papers,
            "missing_paper_ids": missing_ids,
            "missing_bibtex_paper_ids": missing_bibtex_ids,
            "bibtex_entries": entries,
        },
        warnings=warnings,
        bibtex_text=bibtex_text,
    )


def _duplicate_bibtex_keys(entries: Sequence[str]) -> list[str]:
    keys: list[str] = []
    for entry in entries:
        match = re.search(r"@[^\s{]+\s*\{\s*([^,\s]+)\s*,", entry, re.IGNORECASE)
        if match:
            keys.append(match.group(1))
    seen: set[str] = set()
    duplicates: list[str] = []
    for key in keys:
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    return duplicates


def _recommend(args: argparse.Namespace, client: S2Client) -> CommandResult:
    positive_ids = _dedupe(args.positive_id)
    negative_ids = _dedupe(args.negative_id)
    overlap = sorted(set(positive_ids) & set(negative_ids))
    if overlap:
        raise ValidationError(
            "positive and negative seeds cannot overlap", field="negative_id"
        )
    params = {"fields": RECOMMENDATION_FIELDS, "limit": args.limit}
    if len(positive_ids) == 1 and not negative_ids:
        pool = args.pool or "all-cs"
        params["from"] = pool
        response = client.recommendations_get(
            f"/papers/forpaper/{quote(positive_ids[0], safe='')}",
            params=params,
        )
        mode = "single"
    else:
        if args.pool is not None:
            raise ValidationError(
                "--pool is supported only for one positive seed and no negative seeds",
                field="pool",
            )
        pool = None
        response = client.recommendations_post(
            "/papers/",
            params=params,
            json_body={
                "positivePaperIds": positive_ids,
                "negativePaperIds": negative_ids,
            },
        )
        mode = "multi"
    papers = normalize_papers(
        response.get("recommendedPapers") if isinstance(response, dict) else None
    )
    warnings: list[str] = []
    if not papers:
        warnings.append(
            "Recommendations returned no papers; reconsider seeds or use all-cs for a single seed"
        )
    missing_bibtex = sum(1 for paper in papers if not paper.get("bibtex"))
    if missing_bibtex:
        warnings.append(
            f"{missing_bibtex} recommendation(s) did not include Semantic Scholar BibTeX"
        )
    return CommandResult(
        result={
            "mode": mode,
            "pool": pool,
            "positive_paper_ids": positive_ids,
            "negative_paper_ids": negative_ids,
            "papers": papers,
        },
        warnings=warnings,
    )


def _edges(args: argparse.Namespace, client: S2Client, *, kind: str) -> CommandResult:
    params: dict[str, Any] = {
        "fields": EDGE_FIELDS,
        "limit": args.limit,
        "offset": args.offset,
    }
    if kind == "citations" and args.publication_date_or_year:
        params["publicationDateOrYear"] = args.publication_date_or_year
    response = client.graph_get(
        f"/paper/{quote(args.paper_id, safe='')}/{kind}",
        params=params,
    )
    paper_key = "citingPaper" if kind == "citations" else "citedPaper"
    edges = normalize_edges(
        response.get("data") if isinstance(response, dict) else None,
        paper_key=paper_key,
    )
    warnings = [f"No {kind} were returned"] if not edges else []
    return CommandResult(
        result={
            "paper_id": args.paper_id,
            "offset": response.get("offset")
            if isinstance(response, dict)
            else args.offset,
            "next": response.get("next") if isinstance(response, dict) else None,
            "data": edges,
        },
        warnings=warnings,
    )


def _snippets(args: argparse.Namespace, client: S2Client) -> CommandResult:
    query = _require_query(args.query)
    paper_ids = _dedupe(args.paper_id)
    if len(paper_ids) > 100:
        raise ValidationError(
            "snippets accepts at most 100 paper IDs", field="paper_id"
        )
    params: dict[str, Any] = {"query": query, "limit": args.limit}
    if paper_ids:
        params["paperIds"] = ",".join(paper_ids)
    if args.year:
        params["year"] = args.year
    response = client.graph_get("/snippet/search", params=params)
    data = normalize_snippets(
        response.get("data") if isinstance(response, dict) else None
    )
    warnings = ["Snippet search returned no matches"] if not data else []
    return CommandResult(
        result={
            "query": query,
            "paper_ids": paper_ids,
            "total": response.get("total") if isinstance(response, dict) else None,
            "data": data,
        },
        warnings=warnings,
    )


def execute(args: argparse.Namespace, client: S2Client) -> CommandResult:
    if args.command == "search":
        return _search(args, client)
    if args.command == "resolve":
        return _resolve(args, client)
    if args.command == "bib":
        return _bib(args, client)
    if args.command == "recommend":
        return _recommend(args, client)
    if args.command == "citations":
        return _edges(args, client, kind="citations")
    if args.command == "references":
        return _edges(args, client, kind="references")
    if args.command == "snippets":
        return _snippets(args, client)
    raise ValidationError(f"Unknown command: {args.command}")


def _arguments_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {key: value for key, value in vars(args).items() if key not in {"force"}}


def _error_envelope(
    error: AgentError,
    *,
    command: str | None,
    arguments: dict[str, Any] | None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command or "unknown",
        "status": "error",
        "arguments": arguments or {},
        "meta": meta or {"api_requests": 0, "retries": 0, "rate_limited": False},
        "error": error.to_dict(),
    }


def _success_envelope(
    args: argparse.Namespace,
    result: CommandResult,
    client: S2Client,
    *,
    authenticated: bool,
) -> dict[str, Any]:
    meta = client.stats.to_dict()
    meta["authenticated"] = authenticated
    return {
        "schema_version": SCHEMA_VERSION,
        "command": args.command,
        "status": "ok",
        "arguments": _arguments_payload(args),
        "meta": meta,
        "result": result.result,
        "warnings": result.warnings,
    }


def _preflight_output(
    path_value: str | None, *, force: bool, field: str
) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.parent.is_dir():
        raise OutputError("Output parent directory does not exist", path=str(path))
    if path.exists() and not force:
        raise OutputError(
            f"{field} already exists; pass --force to replace it", path=str(path)
        )
    if path.is_dir():
        raise OutputError(f"{field} points to a directory", path=str(path))
    return path


def _atomic_write(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise OutputError(
            "Output file appeared before write; refusing to replace it", path=str(path)
        )
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        if path.exists() and not force:
            raise OutputError(
                "Output file appeared before replacement; refusing to replace it",
                path=str(path),
            )
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise OutputError(f"Could not write output: {exc}", path=str(path)) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _print_envelope(envelope: dict[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(envelope, ensure_ascii=True, separators=(",", ":")) + "\n"
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    client_factory: Callable[[str | None, float], S2Client] | None = None,
) -> int:
    parser = build_parser()
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    command_hint = raw_argv[0] if raw_argv and not raw_argv[0].startswith("-") else None
    args: argparse.Namespace | None = None
    client: S2Client | None = None
    try:
        args = parser.parse_args(raw_argv)
        output_path = _preflight_output(args.output, force=args.force, field="output")
        bib_output_path = _preflight_output(
            getattr(args, "bib_output", None),
            force=args.force,
            field="bib-output",
        )
        api_key, requests_per_second = _load_environment()
        if client_factory is None:
            client = S2Client(api_key=api_key, requests_per_second=requests_per_second)
        else:
            client = client_factory(api_key, requests_per_second)
        result = execute(args, client)
        envelope = _success_envelope(
            args, result, client, authenticated=bool(api_key and api_key.strip())
        )
        serialized = json.dumps(envelope, ensure_ascii=False, indent=2) + "\n"
        if output_path is not None:
            _atomic_write(output_path, serialized, force=args.force)
        if bib_output_path is not None:
            _atomic_write(bib_output_path, result.bibtex_text or "", force=args.force)
        _print_envelope(envelope)
        return 0
    except AgentError as exc:
        meta = client.stats.to_dict() if client is not None else None
        envelope = _error_envelope(
            exc,
            command=getattr(args, "command", None) or command_hint,
            arguments=_arguments_payload(args) if args is not None else None,
            meta=meta,
        )
        _print_envelope(envelope)
        return 2 if exc.category in {"validation", "output"} else 3
    except Exception as exc:  # Keep the machine contract even for unexpected failures.
        error = AgentError(
            "Unexpected internal error",
            category="internal",
            details={"type": type(exc).__name__},
        )
        meta = client.stats.to_dict() if client is not None else None
        envelope = _error_envelope(
            error,
            command=getattr(args, "command", None) or command_hint,
            arguments=_arguments_payload(args) if args is not None else None,
            meta=meta,
        )
        _print_envelope(envelope)
        return 3
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    raise SystemExit(main())
