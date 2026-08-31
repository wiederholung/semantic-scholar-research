# Semantic Scholar Research

An unofficial, local-first research plugin for Codex and Claude Code. It searches and disambiguates papers, expands related work, traces citations and references, retrieves snippet evidence, and exports Semantic Scholar-provided BibTeX without sending your API key to another service.

## Install

Prerequisites: [uv](https://docs.astral.sh/uv/) and Python 3.11 or newer. A Semantic Scholar API key is recommended but not required for most endpoints.

### Codex

```shell
codex plugin marketplace add wiederholung/semantic-scholar-research && codex plugin add semantic-scholar-research@wiederholung-semantic-scholar
```

Start a new Codex task after installation so the bundled skill is loaded.

### Claude Code

```shell
claude plugin marketplace add wiederholung/semantic-scholar-research && claude plugin install semantic-scholar-research@wiederholung-semantic-scholar
```

Run `/reload-plugins` if Claude Code asks you to activate the installed plugin.

The chained commands work in Bash, zsh, and PowerShell 7+. In Windows PowerShell 5.1, run the two commands separately.

## Authentication

Set the key in the process environment or in the active project's `.env`:

```text
SEMANTIC_SCHOLAR_API_KEY=
SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND=1
```

Never pass the key on a command line or commit `.env`. The CLI sends it only in the `x-api-key` header and excludes it from output.

## Use

Ask Codex or Claude Code to use the Semantic Scholar Research skill. Typical requests include:

- “Find recent papers on multi-agent theory of mind and disambiguate duplicate records.”
- “Trace direct descendants and foundations of DOI:10.1000/example.”
- “Export exact Semantic Scholar BibTeX for these confirmed paper IDs.”

The bundled CLI is also available from a checkout:

```shell
uv run --project plugins/semantic-scholar-research s2-agent search --query "multi-agent theory of mind" --limit 10
```

Normal output is one JSON object. See the [output contract](plugins/semantic-scholar-research/skills/semantic-scholar-research/references/output-contract.md) for result paths and exit codes.

## Evidence limits

Semantic Scholar metadata, abstracts, TLDRs, citation contexts, and snippets are discovery evidence, not proof that the full paper was read or validated. Citation counts and influential-citation flags are signals, not quality judgments. Free-text title matches always require explicit selection before downstream citation or BibTeX work.

## Development

```shell
cd plugins/semantic-scholar-research
uv sync --all-groups
uv run ruff check .
uv run pytest
uv build
```

This project is not affiliated with or endorsed by Semantic Scholar or Ai2. API use and returned data remain subject to the [Semantic Scholar API License Agreement](https://www.semanticscholar.org/product/api/license).

## License

The original code in this repository is available under the [MIT License](LICENSE). Third-party services and dependencies retain their own terms; see [THIRD_PARTY.md](THIRD_PARTY.md).
