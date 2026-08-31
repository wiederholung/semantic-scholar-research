# CLI Output Contract

Every normal invocation prints exactly one ASCII-safe JSON object to stdout. Non-ASCII text is JSON-escaped so Windows consoles cannot corrupt the envelope; a JSON parser restores the original Unicode text.

## Success

```json
{
  "schema_version": "1.0",
  "command": "search",
  "status": "ok",
  "arguments": {},
  "meta": {
    "api_requests": 1,
    "retries": 0,
    "rate_limited": false,
    "authenticated": true
  },
  "result": {},
  "warnings": []
}
```

An empty paper list is a successful response with a warning. Branch on `status`, then inspect `warnings` and command-specific `result` fields.

## Command Result Paths

- `search`: read ranked candidates from `result.papers`.
- `resolve`: read an exact identifier result from `result.paper`; for text, inspect `result.title_match`, `result.alternatives`, and `result.selection_required`.
- `bib`: read normalized papers from `result.papers` and exact strings from `result.bibtex_entries`.
- `recommend`: read Semantic Scholar's ranked recommendations from `result.papers`.
- `citations` and `references`: read normalized edges from `result.data`; the neighboring paper is always at `result.data[].paper`, not the raw API keys `citingPaper` or `citedPaper`.
- `snippets`: read matches from `result.data`, with normalized paper metadata at `result.data[].paper` and raw snippet annotations at `result.data[].snippet`.

## Error

```json
{
  "schema_version": "1.0",
  "command": "recommend",
  "status": "error",
  "arguments": {},
  "meta": {
    "api_requests": 0,
    "retries": 0,
    "rate_limited": false
  },
  "error": {
    "type": "ValidationError",
    "category": "validation",
    "message": "...",
    "details": {}
  }
}
```

Exit codes:

- `0`: successful API/CLI result, including an empty result set.
- `2`: invalid arguments or unsafe output path/overwrite request.
- `3`: authentication, rate-limit, network, protocol, upstream API, or unexpected internal failure.

## File Output

- `--output PATH` writes the same envelope as indented JSON while stdout remains the compact envelope.
- `bib --bib-output PATH` writes only confirmed, API-provided BibTeX entries separated by one blank line.
- Existing files are never replaced unless `--force` is explicit.
- Missing BibTeX and duplicate citation keys produce warnings; the CLI does not synthesize or rewrite entries.
