---
name: semantic-scholar-research
description: Search, disambiguate, recommend, trace, and cite scientific papers through the Semantic Scholar Graph and Recommendations APIs. Use when Codex needs Semantic Scholar literature discovery, official BibTeX, related-work expansion from positive or negative seeds, citation or reference neighborhoods, snippet evidence, or a bounded multi-round literature survey for an AI-agent workflow.
---

# Semantic Scholar Research

Use the bundled machine-oriented CLI to gather Semantic Scholar evidence. Keep semantic choices in the agent: inspect each round, choose seeds deliberately, and never let the CLI silently resolve an ambiguous title.

## Run the CLI

Locate this installed skill directory from the host-provided skill metadata. Walk upward to the nearest directory containing both `pyproject.toml` and `src/semantic_scholar_agent`; that directory is `<plugin-root>`. Run:

```text
uv run --project <plugin-root> python <skill-dir>/scripts/run.py <command> [arguments]
```

Parse the single JSON object printed to stdout. Branch on `status`; do not scrape stderr. Read [references/output-contract.md](references/output-contract.md) when implementing a consumer or debugging a result shape.

Read neighboring papers from `result.data[].paper` for both `citations` and `references`; the CLI deliberately normalizes away the raw `citingPaper` and `citedPaper` keys.

Never pass an API key on the command line or print it. Let the CLI read `SEMANTIC_SCHOLAR_API_KEY` from the process environment, the active project's `.env`, or the plugin development root's `.env`, in that order. Run calls sequentially.

## Choose a Command

- Search a topic: `search --query "..." --limit 10` plus optional year, field, venue, publication-type, citation-count, and open-access filters.
- Resolve a remembered title, DOI, arXiv ID, URL, or other identifier: `resolve --query "..."`.
- Export confirmed citations: repeat `bib --paper-id <canonical-id>` and add `--bib-output <path>` only after checking the candidate.
- Expand one seed: `recommend --positive-id <id>`; this uses `all-cs` unless `--pool recent` is explicit.
- Expand multiple positive/negative seeds: repeat `--positive-id` and `--negative-id`; do not pass `--pool` because the multi-seed API has no pool parameter.
- Trace later work: `citations --paper-id <id>`.
- Trace foundations: `references --paper-id <id>`.
- Check topical evidence: `snippets --query "..." --paper-id <id>`; repeat paper IDs as needed.

Use canonical 40-character Semantic Scholar paper IDs for `bib`, `recommend`, `citations`, `references`, and restricted `snippets`. Run `search` or `resolve` first when starting with text or an external identifier.

## Conduct a Bounded Literature Survey

1. State the research topic, filters, and exclusions. Default to at most 12 actual API requests and two recommendation rounds unless the user requests another budget.
2. Search for 10-20 candidates. Inspect title, authors, year, abstract or TLDR, external IDs, and rank. Treat every free-text resolution as requiring selection.
3. Select one to three positive seeds. Add negative seeds only to steer away from a clearly irrelevant cluster. Record why each seed was chosen.
4. Request recommendations. Use `all-cs` for a single computer-science seed unless the user specifically wants the recent pool. Preserve Semantic Scholar's returned order.
5. Fetch references for foundational work and citations for descendants. Use snippets only for shortlisted papers whose topical relevance remains unclear.
6. Deduplicate by `paper_id`; then compare DOI and arXiv IDs to detect duplicate records with different S2 IDs. Retain all discovery provenance and source ranks.
7. Repeat with a newly confirmed seed only when the previous round adds a useful direction. Stop when a round yields no new relevant IDs, the topic drifts, or the request budget is reached.
8. Organize the result into direct matches, foundations, descendants, bridge papers found from multiple seeds, recent work, and unresolved candidates. Explain selection from returned evidence; do not invent a composite confidence score.
9. Export BibTeX only for confirmed paper IDs. Preserve the API-provided entry exactly. Report missing entries or duplicate keys instead of rewriting or fabricating them.

## Evidence Boundaries

- Distinguish metadata, S2-generated TLDRs, abstracts, citation contexts, and snippets from full-paper evidence.
- Do not claim to have read or validated full text through this skill.
- Treat citation count and influential-citation flags as discovery signals, not quality verdicts.
- Surface ambiguous matches to the user when selecting the wrong paper would materially affect the result.
- Keep empty results and API warnings visible. An empty `recent` recommendation pool does not mean no related literature exists.

Read [references/api-notes.md](references/api-notes.md) before changing endpoints, fields, limits, identifier handling, or retry behavior.
