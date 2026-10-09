# Visual Culture Collection Pilot

A small, bounded pipeline that collects at most **10** public-domain images, with metadata, from
[The Met Collection API](https://metmuseum.github.io/). Every saved file is validated and recorded.
It validates the pipeline. It is **not** a representative dataset.

## Layout

```
collector.py                 API queries, eligibility checks, bounded downloads, manifest, report
validate_collection.py       manifest / file / hash / image / rights / provenance checks
tests/test_collector.py      unit tests (all HTTP mocked; no network)
requirements.txt             Pillow only; everything else is the standard library
visual_culture_archive/
  images/                    met_<objectID>.<ext>  (actual bytes from images.metmuseum.org)
  metadata/api_snapshots/<run_id>/{objects,search}/*.json   API responses, byte-for-byte
  manifests/collection_manifest.jsonl                       one JSON record per saved image
  logs/collection.log
  reports/COLLECTION_REPORT.md · TEST_RESULTS.md · KNOWN_ISSUES.md · validation_result.json · runs/
```

## Setup (macOS, Python 3.9+)

Everything stays inside this folder. Nothing is installed system-wide.

```bash
cd /Users/cogito/visual-culture-pilot
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Run

```bash
.venv/bin/python -m unittest discover -s tests -v     # 1. unit tests (mocked HTTP)
.venv/bin/python collector.py                         # 2. live run: object 436121 first, then search
.venv/bin/python validate_collection.py               # 3. validate everything on disk
```

The defaults are deliberately conservative:

| Option | Default | Meaning |
|---|---|---|
| `--max-images` | 10 | Hard cap 10; counts only images that were saved *and* validated |
| `--seed-objects` | 436121 | Objects processed before any search |
| `--terms` | poster print typography textile photograph | One `v1/search?q=…&hasImages=true` request per term |
| `--per-term` | 8 | Candidates taken from each term's result list |
| `--max-inspect` | 40 | Upper bound on object-detail requests |
| `--per-class-cap` | 3 | At most 3 picks per Met `classification` (a variety heuristic) |
| `--interval` | 1.0 s | Gap between requests; values below 0.5 s are refused |
| `--timeout` | 30 s | Per-request socket timeout (download overall: 180 s) |
| `--max-image-mb` | 40 | Larger images are refused |
| `--plan-only` | off | Select candidates and save API snapshots, but download nothing |
| `--replay RUN_ID` | – | Re-plan from saved snapshots with no network. Same snapshots, same selection |

Exit codes: `collector.py` returns 0 when at least one image was saved, and 1 when the run was
blocked or saved nothing. `validate_collection.py` returns 0 when every record is valid, 1 on
any error, and 3 when the manifest is missing or empty. An empty manifest is never reported as
a pass.

## What the collector does, per object

1. GET `/public/collection/v1/objects/{id}`. Requests are sequential and spaced at least the
   interval apart. 429/5xx are retried at most twice, honouring `Retry-After`; a `Retry-After`
   longer than 60 s gives up instead of waiting. 4xx and proxy/policy denials are never retried.
2. Save the response bytes unchanged under `metadata/api_snapshots/<run_id>/objects/`.
3. Check eligibility. Rights come first: `isPublicDomain` must be the boolean `true`. A missing
   or non-boolean value counts as *rights uncertain*. Then `primaryImage` must be a non-empty
   `https://images.metmuseum.org/...` URL.
4. Download only from that URL. Redirects are followed only to approved Met hosts. The body is
   streamed into a `.tmp-*.part` file with a size cap.
5. Reject the file if the status is not 200, the Content-Type is not `image/*`, the body looks
   like HTML/XML/JSON, the file is empty, the length is short of `Content-Length`, Pillow cannot
   fully decode it (`verify()` + `load()`), or its SHA-256 matches an image already saved.
6. Atomically place the file as `met_<objectID>.<ext>`. The name comes from the integer ID and
   the format Pillow detected. An existing file is **never** overwritten.
7. Re-hash the placed file, and only then append the manifest record.

## Manifest record

The required fields are `record_id`, `title`, `creator`, `creation_year`, `publication_year`,
`country_or_region`, `genre`, `medium`, `source_institution`, `source_record_url`,
`original_image_url`, `local_file_path`, `is_public_domain`, `license`, `license_evidence_url`,
`attribution_text`, `collected_at`, `sha256`, `file_size_bytes`, `image_validation_status`,
`metadata_confidence` and `context_claims`. These extra fields are added for auditability:

- `rights_evidence` keeps the object-level fact (`isPublicDomain` from this object's API record)
  separate from the general policy statement (the Open Access policy's CC0 designation).
- `field_provenance` records where each field came from (`api:<field>`, `pipeline` or `policy`).
- `metadata_snapshot_path` and `metadata_snapshot_sha256` point to the exact API response.
- `creation_date_text` holds the raw `objectDate`. `creation_year` is set only when that text is
  a bare year, such as `1893`.
- `image_format`, `image_width`, `image_height`, `api_record_url` and `selection` are also added.

`local_file_path` is relative to `visual_culture_archive/`. Unavailable values are `null`, and
nothing is inferred. `context_claims` is always `[]`. The validator rejects any claim that has no
`source_citation`.

## Limitations

See `visual_culture_archive/reports/KNOWN_ISSUES.md`.
