# Known issues, limitations and status

## Status by feature

| Status | Feature |
|---|---|
| **Implemented and tested (offline)** | source registry + policy reviews with evidence; sitemap (index, gzip, image:image) / RSS / Atom / HTML-link / JSON-catalog discovery; URL normalization and dedup; page metadata extraction (JSON-LD, OG, Twitter, meta, DOM); canonical/alias/content-hash page dedup; 10 design features with observed/inferred/unverified evidence; SSRF guards; robots.txt; rate limit; bounded retries with Retry-After; bounded redirects re-checked on every hop; policy-gated streaming image download with MIME/magic/end-marker/Pillow validation; SHA-256 content-addressed storage; same-file-many-records dedup; write-ahead journal + `repair`; `verify` (missing/corrupt/relocated/orphans); `deduplicate`; keyword search with filters and explanations; validated JSON export/import; genres (tree, many-to-many); years only from explicit data; measured features (header always, colour/brightness with Pillow) + thumbnails; semantic features with AI/human/reviewed separation; research sources, claims, claim↔source evidence with access level, context records, asset↔context relations with enforced rules; trend comparison / frequency / emergence / common features / timeline with sample-size guards; design projects + 9-section report (markdown/json/html); local web UI (6 screens); logging with secret redaction; CLI with exit codes |
| **Partially implemented** | **Typography** is observed only from CSS source declarations (font-family, Google Fonts links), never from rendering. **Visual hierarchy** is only the DOM heading outline (labelled inferred). **Image type** comes from keyword rules or a source-declared value, with no visual classification. The **JSON-catalog adapter** maps fields from one JSON document; it cannot build URLs (e.g. IIIF) or page through an API. **Web UI** offers only some editing: create a project, add references, notes and contexts, and generate a report. Asset metadata, features, claims and policy decisions are edited through the CLI only. |
| **Planned / extension points (not implemented)** | rendered-layout analysis (grid, whitespace, rendered hierarchy, page screenshots); AI-generated semantic suggestions (storage and review exist, but no model is called); vector/embedding search (`SearchBackend` interface exists); JSON Schema file for `magazine_image_reference/1` (the Python validator is authoritative); InDesign UXP / orchestrator integration (only the JSON contracts and the `--json` CLI exist); per-API adapters (Met, AIC, Europeana, ...); HTTP proxy support in `SafeTransport`; authentication on the web UI |
| **Unverified** | every behaviour against **real** websites and APIs (no outbound access here); `pip install -e .` with build isolation; running under pytest; Python 3.10 or older (3.11 and 3.13 tested); browser rendering of the UI |

## Limitations to know before a live run

- **No proxy support.** `SafeTransport` connects directly so that it can pin and verify the
  destination IP. Behind a mandatory HTTP(S) proxy, live collection fails with connection errors.
  Those failures are recorded as transient and nothing is bypassed.
- **robots.txt is fetched per origin**, including image hosts. A 5xx or unreachable robots.txt
  blocks that origin, as RFC 9309 requires.
- **Non-standard ports are refused** for remote hosts (SSRF hardening). For example, a
  `https://example.org:8443` source is not allowed.
- `same_site` treats `www.example.org` and `example.org` as one site. Other subdomains (e.g. a
  CDN) must be listed in `allowed_asset_hosts`.
- **Header probes during crawl.** With `MAGREF_IMAGE_MODE=header` (the default), crawl reads up
  to 64 KB of each of the first 3 images on a page to measure dimensions. This applies to sources
  with policy `unknown` too, but never `restricted`, and nothing is stored on disk. Set
  `MAGREF_IMAGE_MODE=off` if even that is unwanted.
- The **page `published_at`** of a crawled article is stored as the image's `upload_date`, the
  date it went online. It is deliberately not used as the work's publication or creation date.
- **Keyword search is lexical.** "minimalist" matches "minimal" through light suffix stripping;
  synonyms do not match. It searches stored text and labels, so it finds "whitespace" only where a
  page's metadata or text says so.
- **Trends describe the collection only.** With the bundled fixtures, the results are artefacts
  of synthetic data.
- **Data-root moves.** `verify --all` reports files found at the same relative path under the new
  root as `relocated`. `verify --all --relocate` accepts them after re-hashing. Files moved
  elsewhere show up as `missing`.
- **Concurrency.** Page fetching uses a thread pool (`MAGREF_MAX_CONCURRENCY`). Downloads are
  sequential. All SQLite writes happen on one thread.
- The **web UI** has no authentication and binds 127.0.0.1 by default. `serve --host 0.0.0.0`
  prints a warning; do not expose it.

## Unresolved defects

None known at the time of handoff. All 73 tests and all 42 acceptance checks pass in the
development container. Report anything found as a defect against `HANDOFF.md`'s acceptance procedure.
