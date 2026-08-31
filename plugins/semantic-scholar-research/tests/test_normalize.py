from __future__ import annotations

from semantic_scholar_agent.normalize import (
    normalize_edges,
    normalize_paper,
    normalize_snippets,
)


def test_normalize_paper_preserves_bibtex(paper_record: dict[str, object]) -> None:
    paper = normalize_paper(paper_record)
    assert paper is not None
    assert paper["bibtex"] == paper_record["citationStyles"]["bibtex"]  # type: ignore[index]
    assert paper["authors"] == [{"author_id": "1", "name": "Ada Example"}]


def test_normalize_citation_edge(paper_record: dict[str, object]) -> None:
    edges = normalize_edges(
        [
            {
                "contexts": ["uses this method"],
                "intents": ["Methodology"],
                "contextsWithIntent": [
                    {"context": "uses this method", "intents": ["methodology"]}
                ],
                "isInfluential": True,
                "citingPaper": paper_record,
            }
        ],
        paper_key="citingPaper",
    )
    assert edges[0]["is_influential"] is True
    assert edges[0]["paper"]["paper_id"] == paper_record["paperId"]


def test_normalize_snippet_keeps_raw_annotation(
    paper_record: dict[str, object],
) -> None:
    snippets = normalize_snippets(
        [
            {
                "score": 0.8,
                "paper": paper_record,
                "snippet": {"text": "evidence", "annotations": {"sentences": []}},
            }
        ]
    )
    assert snippets[0]["snippet"]["text"] == "evidence"
    assert snippets[0]["paper"]["title"] == "A Test Paper"
