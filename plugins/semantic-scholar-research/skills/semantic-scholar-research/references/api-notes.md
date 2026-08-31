# Semantic Scholar API Notes

## Sources

- Tutorial: <https://www.semanticscholar.org/product/api/tutorial>
- Academic Graph API: <https://api.semanticscholar.org/api-docs>
- Recommendations API: <https://api.semanticscholar.org/api-docs/recommendations>
- API service status: <https://status.api.semanticscholar.org/>

Treat the checked-in OpenAPI specifications under `ref/s2_api_openapi_spec/` as development snapshots, then verify breaking changes against the official documentation.

## Authentication and Rate Control

- Send `SEMANTIC_SCHOLAR_API_KEY` only as the case-sensitive `x-api-key` header.
- Default to one request per second across endpoints. Override `SEMANTIC_SCHOLAR_REQUESTS_PER_SECOND` only when Semantic Scholar has granted a higher rate.
- Retry `429`, `500`, `502`, `503`, and `504`. Honor `Retry-After` up to 30 seconds and return a structured error instead of blocking longer.
- Avoid parallel requests. Prefer batch endpoints where the command supports them.

## Endpoint Selection

| Capability | Endpoint | Important behavior |
| --- | --- | --- |
| Bounded ranked search | `GET /graph/v1/paper/search` | Maximum 100 per response and 1,000 relevance-ranked results. |
| Closest title | `GET /graph/v1/paper/search/match` | Returns one title match and an opaque `matchScore`; do not interpret it as a probability. |
| Direct details | `GET /graph/v1/paper/{paper_id}` | Accepts S2 and supported external identifiers. |
| Confirmed BibTeX batch | `POST /graph/v1/paper/batch` | Maximum 500 IDs; request `citationStyles`. Match canonical IDs explicitly rather than trusting response order. |
| Citations | `GET /graph/v1/paper/{paper_id}/citations` | Request contexts, intents, influence, and citing-paper fields. |
| References | `GET /graph/v1/paper/{paper_id}/references` | Request contexts, intents, influence, and cited-paper fields. |
| Snippets | `GET /graph/v1/snippet/search` | Restrict to about 100 paper IDs when needed. |
| Single-seed recommendation | `GET /recommendations/v1/papers/forpaper/{paper_id}` | Supports `from=recent|all-cs`; `recent` is the API default, but this skill defaults to `all-cs`. |
| Multi-seed recommendation | `POST /recommendations/v1/papers/` | Accepts positive and negative ID arrays; does not expose the single-seed pool parameter. |

## Paper Fields

Request only the fields required for agent judgment and citation export:

`paperId,corpusId,externalIds,url,title,abstract,tldr,venue,publicationVenue,year,publicationDate,journal,authors,citationCount,influentialCitationCount,referenceCount,fieldsOfStudy,publicationTypes,isOpenAccess,openAccessPdf,citationStyles`

`citationStyles.bibtex` is Semantic Scholar's BibTeX. Preserve it exactly and return `null` when absent.

## Identifier Policy

Allow `resolve` to accept titles, DOI, arXiv, CorpusId, S2 IDs, and supported URLs. Return the canonical `paper_id`. Require that canonical ID for all downstream seed and export commands so that title ambiguity and batch-order drift cannot attach evidence to the wrong paper.
