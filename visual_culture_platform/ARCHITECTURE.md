# Architecture

## Why this shape

- **Python stdlib only for the core.** sqlite3, urllib/http.client, html.parser and xml.etree are
  enough, and the Antigravity VM can run the project with no dependency resolution at all.
  Pillow is optional: it adds colour and brightness measurement and decode verification. pytest
  and jsonschema are optional for tests.
- **SQLite** is the single store. Migrations are ordered SQL scripts tracked with `PRAGMA user_version`.
- **One CLI, one web UI, one set of repositories.** The UI (`web.py`) is server-rendered HTML on
  `http.server` and calls the same repository classes as the CLI. There is no JavaScript build
  and no second code path. This was chosen because the repository had no UI and the target VM
  should not need a frontend toolchain.
- **Collection and interpretation are separate.** Bytes and metadata that were observed are stored
  apart from interpretations. Interpretations always carry who or what made them and their review
  status.

## Components

```
            sources.fixture.json / `source add`
                          |
                 +--------v---------+      policy_reviews (history)
                 |  registry.py     |<---- `policy-review` (human decision + evidence)
                 +--------+---------+
                          |
   +----------------------v-----------------------+
   | discovery.py  sitemap | rss | html | json_catalog
   |   -> discovered_urls (pages)                  |
   |   -> image_refs      (image candidates)       |
   +------+--------------------------+-------------+
          |                          |
  +-------v--------+        +--------v----------+
  | pages.py crawl |        | downloader.py     |  only effective policy 'allowed',
  | extract.py     |        |  stream -> tmp    |  source enabled, host allowed
  | features.py    |        |  validate bytes   |
  | -> refs        |        |  sha256 -> storage|
  | -> image_refs  |        |  journal -> DB    |
  +-------+--------+        +--------+----------+
          |                          |
          |      +-------------------v-----------+
          |      | storage.py   (content-addressed files)
          |      | maintenance.py verify/repair/dedup/orphans
          |      +-------------------+-----------+
          |                          |
          |                 +--------v---------+
          |                 | analysis.py      |  measured features from stored bytes
          |                 +--------+---------+
          v                          v
   +------+--------------------------+-----------------------------+
   | search.py (keyword)  export.py (validated JSON)  trends.py     |
   | research.py (genres, semantic features, sources, claims,       |
   |              contexts, asset-context relations)                |
   | projects.py (workspace + 9-section report)                     |
   +------+---------------------------------------------------------+
          |
     cli.py  /  web.py (127.0.0.1)
```

All HTTP goes through `http.Fetcher`, which wraps a `Transport`:

| Transport | Used for |
|---|---|
| `SafeTransport` | Real network. Resolves DNS, rejects any non-public answer, connects to the vetted IP and re-checks the socket peer. Does not use proxies. |
| `FixtureTransport` | `--fixtures DIR`. Serves `https://<host>/<path>` from `DIR/<host>/<path>`, with optional `_fixture.json` overrides for status codes and redirects. |
| test `MockTransport` / local server | Unit tests (`tests/helpers.py`). |

`Fetcher` applies the following to **every hop, including redirect targets**:

- URL safety (`netsafe.check_url`)
- the caller's policy hook (for downloads: the host must be the source site or one of its `allowed_asset_hosts`)
- robots.txt (RFC 9309: 4xx means no robots file; 5xx or unreachable means disallow all)
- per-host request interval, raised to Crawl-delay when that is larger
- bounded retries for 408/429/500/502/503/504 and timeouts, with exponential backoff and
  Retry-After honoured up to a cap
- at most 5 redirects, with loop detection
- a response size cap

## Data flow details

**Discovery.** Discovery never downloads images and never follows links recursively. HTML
discovery reads only the source's entry pages, and only links on the same host; it honours
`rel=nofollow` and meta `nofollow`. URLs are normalized (`urls.py`), so tracking parameters,
fragments, default ports, case and dot-segments do not create duplicates.

**Crawl (pages).** For each pending discovered URL, crawl does the following:

1. Fetch the page. Non-HTML responses and `noindex` pages are skipped.
2. Extract metadata. The precedence is JSON-LD > Open Graph > Twitter > meta > elements, and the
   winning source of every field is kept.
3. Optionally read at most 64 KB of the first images to measure their dimensions. Nothing is
   written to disk.
4. Build the ten design features with evidence levels.
5. Store the page reference, keyed by canonical URL. An alternate URL (AMP, tracking variant) is
   recorded as an alias and never overwrites the canonical record. Images on the page become
   image candidates.

**Download.** The steps are:

1. Policy gate.
2. Stream to `tmp/*.part`, with the size cap and the run's byte budget checked on every chunk.
3. Validate the bytes: non-empty, Content-Length matches, magic bytes identify a supported format,
   the declared MIME type agrees, the end-of-file marker is present, and Pillow can decode the
   file (when installed).
4. Compute SHA-256. If those bytes are already stored, link the record to the existing file.
5. Otherwise write a journal entry, `os.replace` the file into
   `images/<publisher>/<year>/<sha[:2]>/<sha>.<ext>`, commit the DB rows, and delete the journal.

`repair` replays journals left behind by a crash between the move and the commit. Temp files are
deleted on every failure path.

**Failure classes.**

- *Transient* (retried within limits; picked up again by `retry --failed`): timeouts, connection
  errors, 408, 429, 5xx, interrupted streams, Content-Length mismatch.
- *Permanent* (never retried automatically): 4xx, wrong content type, HTML disguised as an image,
  unsupported format, too large, truncated or corrupt image, MIME mismatch.
- *Blocked* (status `blocked`): any policy or network-safety refusal. These items become eligible
  again only after a policy or configuration change, or an explicit `reset`.

**Integrity.** `verify --all` re-hashes every stored file:

- missing file → `missing`; corrupt file → moved to `quarantine/corrupt` (never deleted).
  Either way, its assets become `missing_file`, and `retry --failed --include-missing` restores them.
- file found only under a new data root → `relocated` (`--relocate` accepts it after re-hashing).
- orphan files (on disk but not in the DB) are reported only, never deleted.

## Module responsibilities

| File | Responsibility |
|---|---|
| `config.py` | settings from env / `.env` / flags, validation |
| `timeutil.py` | UTC timestamps, date normalization (ISO 8601 / RFC 2822) |
| `urls.py` | URL normalization, stable IDs, redaction for logs |
| `netsafe.py` | SSRF checks (scheme, credentials, host names, IP classes, DNS answers, ports) |
| `http.py` | transports, robots, rate limit, retries, redirects, size limits |
| `db.py` | schema + migrations (v1 collection, v2 research platform) |
| `registry.py` | sources, policy reviews, effective policy per image, unblocking on change |
| `discovery.py` | sitemap / RSS / HTML / JSON-catalog adapters, safe XML parsing |
| `extract.py` | HTML metadata extraction (JSON-LD, OG, Twitter, meta, DOM stats, images) |
| `features.py` | 10 design features with observed / inferred / unverified evidence; image-type rules |
| `pages.py` | crawl + page-reference persistence and dedup |
| `assets.py` | image references (assets): upsert, years from explicit data only, status transitions |
| `downloader.py` | policy-gated streaming download, validation, dedup, journal |
| `storage.py` | data-root layout, safe paths, atomic placement, journal files |
| `maintenance.py` | verify, orphans, repair, deduplicate, temp cleanup |
| `images.py` | format sniffing, header dimensions, end-marker check, Pillow helpers |
| `analysis.py` | measured features from stored files |
| `research.py` | genres, semantic features + review, research sources, claims, contexts, relations |
| `trends.py` | period comparison, frequency, emergence, common features, timeline (descriptive) |
| `projects.py` | design projects, report builder (markdown / json / html) |
| `search.py` | keyword search behind a `SearchBackend` interface |
| `models.py`, `image_contract.py`, `export.py` | contracts, validation, export/import |
| `cli.py`, `web.py`, `logutil.py`, `app.py` | interfaces, logging redaction, wiring |

## Extension points (not implemented)

- `SearchBackend`: an embedding or vector backend can implement `search(SearchQuery)` beside
  `KeywordSearch`.
- Rendered-layout analysis (grid, whitespace, rendered hierarchy) would fill the features that are
  `unverified` today.
- AI semantic suggestions: `FeatureRepo.add_semantic(origin="ai", tool=...)` stores them as
  `ai_suggested` until a human reviews them. No model is called by this code.
- External orchestrator / InDesign UXP plugin: consume `magref --json ...` or the export files
  (`magazine_reference/1`, `magazine_image_reference/1`). No integration exists yet.
