# Known Issues

## Blockers (observed)

| # | Blocker | Exact evidence | Remedy |
|---|---|---|---|
| B1 | The Met API is unreachable from this container | `Tunnel connection failed: 403 Forbidden` for `collectionapi.metmuseum.org` | Run on a machine that reaches the API (you report HTTP 200 on the Mac), or allow the host in the cloud environment's network policy |
| B2 | The Met image host is unreachable from this container | `network_blocked: Tunnel connection failed: 403 Forbidden` for `images.metmuseum.org` | Same as B1 |
| B3 | Pillow cannot be installed for Python 3.9 here | direct: `Name or service not known` (pypi.org is on NO_PROXY, and there is no direct DNS); through the proxy: `pypi.org:443 connect_rejected` (403) | On the Mac: `python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt` |
| B4 | The target Mac directory `/Users/cogito/visual-culture-pilot` is not visible to this session | `ls: cannot access '/Users'` | Copy this project folder to the Mac and run the commands in README.md |

Process note: one install attempt passed `NO_PROXY=localhost,127.0.0.1` to `uv` for a single
command, so that the request went *through* the configured proxy. It was denied (403). That was
before the instruction not to change proxy settings. Nothing was changed persistently, and no
further attempts were made.

## Unverified assumptions

- **API docs were not read in full.** `metmuseum.github.io` is blocked here (and failed via
  WebFetch as well). The endpoint paths and fields are taken from your brief and from web-search
  snippets: `objectIDs`, `isPublicDomain`, `primaryImage`, `objectURL`, `objectDate`,
  `artistDisplayName`, `classification`, `medium`, `country`, `region` and `creditLine`. The
  parser fails closed (`unexpected_schema`) if the shape differs.
- **Search endpoint.** On the Mac run of 2026-10-09 (user-reported output), every
  `v1/search` request returned **HTTP 410**. Met documentation, seen only as search-result
  snippets, says v1/search was retired on 2026-10-01. It also says `v1.1/search` takes the same
  filters plus `offset` (0-based) and `limit` (default 100, max 500), and returns `total` and
  this page's `objectIDs`. The collector now uses `v1.1/search` with `offset=0&limit=<per-term>`
  (one page per term). It has **not yet been observed live**. If the response shape differs,
  the parser fails closed with `unexpected_schema`. HTTP 410 is now its own category
  (`endpoint_gone`) and is not retried.
- **The CC0 inference links two statements.** The first is the object-level `isPublicDomain: true`
  from the API. The second is the general Open Access policy
  (https://www.metmuseum.org/about-the-met/policies-and-documents/open-access). That policy page
  could not be fetched here; its CC0 wording was seen only in search snippets. The record keeps
  the two apart (`rights_evidence.license_basis = "general_policy_statement"`).
- **Search order stability.** Selection is deterministic given saved responses (`--replay`).
  Whether the live API returns the same order next week is unknown.
- **`genre` = Met `classification`.** This is a cataloguing class, not a genre judgement.
- **Variety.** The per-classification cap (3) and the title/artist/classification near-duplicate
  key are heuristics. Duplicate detection is by exact SHA-256 only; there is no perceptual
  hashing, so visually near-identical images with different bytes are not caught.

## Design limits

- `publication_year` is always `null`: the object API has no such field.
- `creation_year` is filled only when `objectDate` is a bare year. Ranges and "ca." dates stay
  `null`, with the raw text kept in `creation_date_text`.
- The image size cap defaults to 40 MB. Some Met originals may be larger and would be refused
  (`too_large`). Raise `--max-image-mb` if needed.
- macOS system Python 3.9.6: if HTTPS fails with `CERTIFICATE_VERIFY_FAILED`, that is a local
  certificate-store issue. Do not disable verification.
- `logs/collection.log` is appended across runs. Each run has its own JSON under `reports/runs/`.
