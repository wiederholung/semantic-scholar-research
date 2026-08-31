from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def canonical_id() -> str:
    return "a" * 40


@pytest.fixture
def second_id() -> str:
    return "b" * 40


@pytest.fixture
def paper_record(canonical_id: str) -> dict[str, Any]:
    return {
        "paperId": canonical_id,
        "corpusId": 123,
        "externalIds": {"DOI": "10.1000/example"},
        "url": f"https://www.semanticscholar.org/paper/{canonical_id}",
        "title": "A Test Paper",
        "abstract": "A test abstract.",
        "tldr": {"text": "A short summary."},
        "venue": "TestConf",
        "publicationVenue": {"name": "Test Conference", "type": "conference"},
        "year": 2024,
        "publicationDate": "2024-01-02",
        "journal": None,
        "authors": [{"authorId": "1", "name": "Ada Example"}],
        "citationCount": 12,
        "influentialCitationCount": 2,
        "referenceCount": 20,
        "fieldsOfStudy": ["Computer Science"],
        "publicationTypes": ["Conference"],
        "isOpenAccess": True,
        "openAccessPdf": {"url": "https://example.test/paper.pdf", "status": "GREEN"},
        "citationStyles": {
            "bibtex": "@inproceedings{Example2024,\n author = {Ada Example},\n title = {A Test Paper},\n year = {2024}\n}"
        },
    }
