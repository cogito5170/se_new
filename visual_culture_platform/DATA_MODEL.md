# Data model

SQLite, schema version 2. `src/magref/db.py` is the source of truth, and `magref init` creates or
upgrades the database. All timestamps are UTC `YYYY-MM-DDTHH:MM:SSZ`. JSON columns hold UTF-8 JSON.

## Entity map (specification name → table)

| Spec entity | Table(s) | Notes |
|---|---|---|
| source | `sources` | discovery config + current policy (`unknown / review_required / allowed / restricted`) |
| policy_review | `policy_reviews` | every decision, with licence, evidence URL, reviewer and time; source- or image-level |
| reference (page) | `refs`, `ref_urls` | one row per canonical page; every URL that led there is in `ref_urls` |
| reference (image) / **Asset** | `image_refs` | one row per normalized image URL, with its own source, page, licence and policy |
| image_asset / content_hash | `image_files` | one row per distinct binary; **primary key = SHA-256**; many `image_refs` → one file |
| download_job | `download_jobs` | one per `download` / `retry` run, with limits and outcome stats |
| download_attempt | `download_attempts` | every HTTP attempt: outcome, error class and code, requested vs final URL, bytes, hash |
| processing_error | `processing_errors` | every recorded failure or warning: stage, code, error class, URL |
| — | `discovered_urls`, `runs` | crawl frontier with per-URL status; run bookkeeping |
| Genre | `genres` (tree via `parent_id`), `asset_genres` (many-to-many) | `assigned_by`: source_declared / human / ai_suggested |
| VisualFeature | `visual_features` | `kind` measured or semantic; method, tool, file hash, confidence, review status |
| ContextRecord | `context_records`, `context_genres`, `context_sources` | period may be unknown or approximate |
| ResearchSource | `research_sources` | type, author, publisher, date, URL, identifier, accessed_at |
| ResearchClaim | `research_claims`, `claim_sources` | claim ↔ source is many-to-many, with relation and **access level read** |
| AssetContextRelation | `asset_context` | relation type + evidence status + optional claim |
| TrendObservation | `trend_observations` | saved comparisons; always start `unverified` |
| DesignProject | `design_projects`, `project_assets`, `project_contexts`, `project_features`, `project_notes`, `project_reports` | |

## Assets (`image_refs` + `image_files`)

| Field (spec) | Column | Rule |
|---|---|---|
| id | `image_refs.id` | `mi_` + first 20 hex of SHA-256(normalized original URL), so it is stable |
| title, description, alt, caption | same | null when unknown |
| local_path | `image_files.abs_path` (+ `rel_path`) | only when downloaded; the relative path is under the data root |
| original_url / final download URL | `url` / `final_url` | kept apart (redirects) |
| source page URL | `source_page_url` | |
| source_id, publisher | same | |
| creator | `creator` | |
| publication_date / creation_date / upload_date | three columns | **never derived from each other** |
| year_start / year_end | same | the work's years, **only from explicit data**; see `year_basis` (`source_declared`, `publication`, `creation`, `circa`). Crawl, discovery and upload dates never produce a year. "c. 1990s" becomes null. |
| country, region | same | |
| genre / sub-genre | `asset_genres` → `genres` tree | e.g. `editorial design/magazine cover` |
| media_type | `media_type` | photograph, illustration, painting, graphic_design, typography, print_scan, mixed, unknown |
| material type | `image_type` + `type_status/method/basis` | cover, interior_page, editorial_photo, portrait, product_photo, other. A source-declared type is observed; a keyword-rule type is inferred; no evidence leaves it unverified. |
| mime_type, width, height, size_bytes, sha256 | `image_files` | measured from the stored bytes |
| rights / licence | effective policy (below) + `declared_license` | a licence declared by a catalog is data, not a review |
| download status | `download_status`, `attempt_count`, `last_attempt_at`, `last_error`, `last_error_class` | |
| analysis status, review status | `analysis_status` (pending / measured / failed / not_applicable), `review_status` (unreviewed / reviewed / needs_attention) | |
| created / first collected | `discovered_at`, `updated_at` | |

**Effective image policy:**

- A `restricted` source cannot be overridden by an image-level review.
- Otherwise the latest image-level review applies.
- Otherwise the source policy applies, and the record says `scope: source`.
- Only `allowed` is downloadable, and setting `allowed` requires a licence or an evidence URL.

**Download status transitions** (`assets.TRANSITIONS`; anything else raises `InvalidTransition`):

```
pending          -> downloaded | failed_transient | failed_permanent | blocked
failed_transient -> downloaded | failed_transient | failed_permanent | blocked | pending
failed_permanent -> pending                 (explicit `magref reset` only)
blocked          -> pending | blocked       (pending again only after a policy/config change or reset)
downloaded       -> missing_file | downloaded
missing_file     -> downloaded | failed_transient | failed_permanent | blocked | pending
```

`image_files.file_status`: ok | missing | corrupt | relocated.

## Visual features (`visual_features`)

| kind | review_status | Written by | Required |
|---|---|---|---|
| measured | auto_measured (or rejected) | `magref analyze` from stored bytes | `tool` and `file_sha256` (DB CHECK) |
| semantic | human_entered → human_reviewed / rejected | `feature add --origin human` | `method` |
| semantic | ai_suggested → human_reviewed / rejected | `feature add --origin ai --tool MODEL` | `tool` (DB CHECK) |

Measured types:

- **Always:** width, height, aspect_ratio, orientation, file_size.
- **With Pillow:** palette, dominant_color, dominant_hue, brightness_mean, brightness_level,
  contrast_rms, contrast_level, saturation_mean, colorfulness, colorfulness_level.
  The thresholds are written into `method`.

Semantic types: style, art_movement, mood, composition, layout_type, typography,
whitespace_density, information_density, medium, lighting, texture, form_rhythm, styling, motif,
color_contrast, cultural_reading.

Trend analysis counts measured and human features. AI suggestions are counted only with `--include-ai`.

## Research

Verification statuses: `verified`, `partially_supported`, `hypothesis`, `unverified`, `contradicted`.

`claim_sources.relation` is one of supports, partially_supports, contradicts or mentions.
`claim_sources.access_level` is one of title_only, abstract, excerpt or full_text.

Enforced rules (Python first, with SQLite triggers as a backstop):

- A claim is inserted `unverified`. A trigger blocks inserting any other status.
- A status change needs a reviewer.
- `verified` needs ≥1 `supports` link read at excerpt or full_text, and no contradicting source
  read beyond its title. A trigger blocks `verified` without such a link.
- `partially_supported` needs a supporting link read beyond its title. `contradicted` needs a
  contradicting link read beyond its title.
- A title-only source may only `mention` a claim.
- A context record's status cannot be stronger than its best claim.
- `asset_context`:
  - `documented_influence` needs a `verified` claim (trigger).
  - `same_period` needs overlapping known years and gets a "not causation" note.
  - `research_hypothesis` has evidence status `hypothesis`.

## Page references (`refs`)

| Area | Columns |
|---|---|
| identity | `id` = `mr_` + 20 hex of SHA-256(normalized canonical URL, or final URL when no canonical) |
| provenance | `url` (identity, UNIQUE), `canonical_url` (UNIQUE when set), `fetched_url`, `discovery_method`, `discovered_from`, `robots_status`, `field_sources` (field → `json-ld:headline` / `og:title` / ...) |
| content | title, description, publisher, category, published_at, modified_at, language, page_type, access, authors[], keywords[] |
| `assets` | images on the page with role, alt, declared or measured dimensions and their source |
| `visual_features` / `analysis` | the 10 design features (see `features.py`) |
| processing | `errors`, `crawl_status`, `analysis_status`, `http_status`, `content_hash`, `extractor_version`, `first_seen_at`, `last_crawled_at` |

## JSON contracts

| Contract | Validator | JSON Schema |
|---|---|---|
| `magazine_reference/1` (page) | `models.validate_reference` | `schema/magazine_reference-1.schema.json` (generated by `magref schema`; a test keeps it in sync) |
| `magazine_image_reference/1` (image/asset) | `image_contract.validate_image_record` | none yet (the Python validator is authoritative) |
| export envelope `magazine_reference_export/1` | `export.validate_export_doc` | — |

The export envelope has the fields `{schema, kind: pages|images, generated_at, generator, count, filters, references[]}`.

Image record outline (all keys always present; unknown values are `null`):

```json
{"schema": "magazine_image_reference/1", "id": "mi_…",
 "image": {"type", "type_evidence": {"status","method","basis"}, "original_url", "final_url",
           "local_path", "relative_path", "mime_type", "width", "height", "size_bytes", "sha256",
           "file_status", "media_type"},
 "work": {"title","creator","description","alt","caption","publication_date","creation_date",
          "upload_date","year_start","year_end","year_basis","country","region","genres"},
 "source": {"source_id","publisher","source_page_url","page_reference_id","discovery_method"},
 "rights": {"policy_status","policy_scope","license","declared_license","evidence_url","reviewed_at","note"},
 "download": {"status","attempt_count","last_attempt_at","last_error","last_error_class"},
 "features": {"measured": [...], "semantic": [...]},
 "duplicates": {"same_file_as": ["mi_…"]},
 "timestamps": {"discovered_at","updated_at"}}
```

Import trusts nothing that would authorise a download. Imported images arrive as `pending`
metadata, and missing sources are created **disabled** with policy `unknown`.
