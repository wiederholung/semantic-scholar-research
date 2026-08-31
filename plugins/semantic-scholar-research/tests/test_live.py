from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from semantic_scholar_agent.client import S2Client
from semantic_scholar_agent.normalize import PAPER_FIELDS


@pytest.mark.live
def test_live_bibtex_and_all_cs_recommendation() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env", override=False)
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if not api_key:
        pytest.skip("SEMANTIC_SCHOLAR_API_KEY is not configured")
    requests_per_second = float(os.getenv("SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND", "1"))
    with S2Client(api_key=api_key, requests_per_second=requests_per_second) as client:
        match = client.graph_get(
            "/paper/search/match",
            params={"query": "Attention Is All You Need", "fields": PAPER_FIELDS},
        )
        paper = match["data"][0]
        assert paper["paperId"]
        assert paper["citationStyles"]["bibtex"].startswith("@")
        recommendations = client.recommendations_get(
            f"/papers/forpaper/{paper['paperId']}",
            params={
                "from": "all-cs",
                "limit": 1,
                "fields": "paperId,title,citationStyles",
            },
        )
        assert isinstance(recommendations["recommendedPapers"], list)
