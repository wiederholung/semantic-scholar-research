# Contributing

Contributions are welcome. Keep the CLI machine-oriented, preserve the single-JSON-object stdout contract, and surface ambiguity rather than silently choosing a paper.

From `plugins/semantic-scholar-research`, run:

```shell
uv sync --all-groups
uv run ruff check .
uv run pytest
uv build
```

Live tests call Semantic Scholar and require `SEMANTIC_SCHOLAR_API_KEY`:

```shell
uv run pytest -m live
```

Never include credentials, API responses containing private data, or copied upstream API specifications in a contribution.
