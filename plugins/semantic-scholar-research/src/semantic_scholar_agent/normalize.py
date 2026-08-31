from __future__ import annotations

from typing import Any

PAPER_FIELDS = ",".join(
    (
        "paperId",
        "corpusId",
        "externalIds",
        "url",
        "title",
        "abstract",
        "tldr",
        "venue",
        "publicationVenue",
        "year",
        "publicationDate",
        "journal",
        "authors",
        "citationCount",
        "influentialCitationCount",
        "referenceCount",
        "fieldsOfStudy",
        "publicationTypes",
        "isOpenAccess",
        "openAccessPdf",
        "citationStyles",
    )
)

# Recommendations uses a smaller BasePaper schema than Graph's FullPaper schema.
RECOMMENDATION_FIELDS = ",".join(
    field for field in PAPER_FIELDS.split(",") if field != "tldr"
)

EDGE_FIELDS = ",".join(
    (
        "contexts",
        "intents",
        "contextsWithIntent",
        "isInfluential",
        RECOMMENDATION_FIELDS,
    )
)


def _authors(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {"author_id": item.get("authorId"), "name": item.get("name")}
        for item in value
        if isinstance(item, dict)
    ]


def normalize_paper(record: Any, *, rank: int | None = None) -> dict[str, Any] | None:
    if not isinstance(record, dict) or not record.get("paperId"):
        return None
    citation_styles = record.get("citationStyles")
    tldr = record.get("tldr")
    normalized: dict[str, Any] = {
        "paper_id": str(record["paperId"]),
        "corpus_id": record.get("corpusId"),
        "external_ids": record.get("externalIds") or {},
        "url": record.get("url"),
        "title": record.get("title"),
        "abstract": record.get("abstract"),
        "tldr": tldr.get("text") if isinstance(tldr, dict) else None,
        "venue": record.get("venue"),
        "publication_venue": record.get("publicationVenue"),
        "year": record.get("year"),
        "publication_date": record.get("publicationDate"),
        "journal": record.get("journal"),
        "authors": _authors(record.get("authors")),
        "citation_count": record.get("citationCount"),
        "influential_citation_count": record.get("influentialCitationCount"),
        "reference_count": record.get("referenceCount"),
        "fields_of_study": record.get("fieldsOfStudy") or [],
        "publication_types": record.get("publicationTypes") or [],
        "is_open_access": record.get("isOpenAccess"),
        "open_access_pdf": record.get("openAccessPdf"),
        "bibtex": citation_styles.get("bibtex")
        if isinstance(citation_styles, dict)
        else None,
    }
    if rank is not None:
        normalized["rank"] = rank
    if "matchScore" in record:
        normalized["match_score"] = record.get("matchScore")
    return normalized


def normalize_papers(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    papers: list[dict[str, Any]] = []
    for rank, record in enumerate(records, start=1):
        paper = normalize_paper(record, rank=rank)
        if paper is not None:
            papers.append(paper)
    return papers


def normalize_edges(records: Any, *, paper_key: str) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    edges: list[dict[str, Any]] = []
    for rank, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        paper = normalize_paper(record.get(paper_key), rank=rank)
        if paper is None:
            continue
        edges.append(
            {
                "rank": rank,
                "contexts": record.get("contexts") or [],
                "intents": record.get("intents") or [],
                "contexts_with_intent": record.get("contextsWithIntent") or [],
                "is_influential": record.get("isInfluential"),
                "paper": paper,
            }
        )
    return edges


def normalize_snippets(records: Any) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        return []
    normalized: list[dict[str, Any]] = []
    for rank, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        snippet = record.get("snippet")
        normalized.append(
            {
                "rank": rank,
                "score": record.get("score"),
                "paper": normalize_paper(record.get("paper")),
                "snippet": snippet if isinstance(snippet, dict) else {},
            }
        )
    return normalized
