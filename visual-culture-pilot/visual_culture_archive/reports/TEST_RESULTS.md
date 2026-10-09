# Test Results

Recorded 2026-10-09 (UTC) in a **Linux cloud container**, not on the target Mac
(`/Users/cogito/visual-culture-pilot`). That machine was not reachable from this session.
Every outcome below is the actual output of a command run here. Nothing is projected.

## Summary

| Category | Mocked unit tests, Python 3.13.16 + Pillow 12.3.0 | Mocked unit tests, Python 3.9.25, no Pillow | Live checks |
|---|---|---|---|
| PASSED  | 52 | 32 | 0 |
| FAILED  | 0 | 0 | 0 |
| BLOCKED | 0 | 0 | 3 (API object request, image-host request, collection run) |
| NOT RUN | 0 | 20 (need Pillow; it could not be installed) | 4 (see below) |

**Validated real images: 0.** The pilot is **not** a success. No real image has been downloaded
or validated.

## 1. Mocked unit tests (no network)

All HTTP traffic is served by an in-process fake opener, and every file is written to a temp dir.

```
$ python3 -m unittest discover -s tests -v          # Python 3.13.16, Pillow 12.3.0
Ran 52 tests in 0.147s

OK

$ .venv/bin/python -m unittest discover -s tests -v  # Python 3.9.25 (project-local venv), no Pillow
Ran 52 tests in 0.018s

OK (skipped=20)
```

Why 3.9 has no Pillow: `uv pip install "Pillow>=10.0,<12"` into the project venv failed.

```
direct:   failed to lookup address information: Name or service not known   (pypi.org is on NO_PROXY; no direct DNS)
proxied:  tunnel error: unsuccessful  -- agent proxy log: pypi.org:443 connect_rejected,
          "gateway answered 403 to CONNECT (policy denial or upstream failure)"
```

The proxy, DNS and NO_PROXY settings were left unchanged, as instructed. The 20 Pillow-dependent
tests were **not run** on 3.9 (skipped), and the summary does not count them as passes. They do
run on 3.13, where Pillow is present.

| Test | Python 3.13 + Pillow | Python 3.9, no Pillow |
|---|---|---|
| `Downloads.test_content_length_mismatch_is_truncation` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Downloads.test_duplicate_sha256_rejected` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Downloads.test_empty_file` | PASSED | PASSED |
| `Downloads.test_garbage_bytes` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Downloads.test_html_body_with_image_content_type` | PASSED | PASSED |
| `Downloads.test_html_error_page_instead_of_image` | PASSED | PASSED |
| `Downloads.test_http_error_on_image` | PASSED | PASSED |
| `Downloads.test_too_large` | PASSED | PASSED |
| `Downloads.test_truncated_image` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Downloads.test_valid_image_saved_atomically_with_hash` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Eligibility.test_bad_schema` | PASSED | PASSED |
| `Eligibility.test_empty_or_missing_image_url` | PASSED | PASSED |
| `Eligibility.test_public_domain_flag` | PASSED | PASSED |
| `Eligibility.test_rights_checked_before_image` | PASSED | PASSED |
| `Eligibility.test_unofficial_image_host` | PASSED | PASSED |
| `FileSafety.test_collector_skips_record_whose_file_already_exists` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `FileSafety.test_existing_file_never_overwritten` | PASSED | PASSED |
| `FileSafety.test_safe_filename` | PASSED | PASSED |
| `Http.test_404_not_retried` | PASSED | PASSED |
| `Http.test_503_honours_retry_after_then_succeeds` | PASSED | PASSED |
| `Http.test_hosts_outside_allowlist_never_requested` | PASSED | PASSED |
| `Http.test_interval_below_floor_rejected` | PASSED | PASSED |
| `Http.test_invalid_json` | PASSED | PASSED |
| `Http.test_long_retry_after_is_not_waited_out` | PASSED | PASSED |
| `Http.test_persistent_5xx_gives_up` | PASSED | PASSED |
| `Http.test_proxy_denial_not_retried` | PASSED | PASSED |
| `Http.test_redirect_to_unapproved_host_refused` | PASSED | PASSED |
| `Http.test_requests_are_spaced` | PASSED | PASSED |
| `Http.test_search_response_parsing` | PASSED | PASSED |
| `MetadataParsing.test_creation_year_only_from_bare_year` | PASSED | PASSED |
| `MetadataParsing.test_empty_strings_are_null_not_invented` | PASSED | PASSED |
| `MetadataParsing.test_missing_optional_fields_become_null` | PASSED | PASSED |
| `MetadataParsing.test_region_used_only_when_country_absent` | PASSED | PASSED |
| `MetadataParsing.test_rights_flag_distinguished_from_general_license` | PASSED | PASSED |
| `MockedRun.test_counts_manifest_and_validation` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `MockedRun.test_max_images_bound` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `MockedRun.test_plan_is_deterministic_round_robin` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `MockedRun.test_rerun_is_idempotent_and_replay_is_deterministic` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Signature.test_jpeg_with_and_without_end_marker` | PASSED | PASSED |
| `Signature.test_png_gif_and_html` | PASSED | PASSED |
| `SourceVersusInterpretation.test_record_carries_no_generated_interpretation` | PASSED | PASSED |
| `SourceVersusInterpretation.test_validator_rejects_uncited_claim_and_non_source_descriptive_value` | PASSED | PASSED |
| `Validator.test_clean_collection_is_valid` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Validator.test_duplicate_hash_across_records` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Validator.test_empty_manifest_is_not_success` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Validator.test_hash_mismatch` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Validator.test_invalid_jsonl_line` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Validator.test_missing_local_file` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Validator.test_no_decoder_means_no_pass` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Validator.test_orphan_image_reported` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Validator.test_path_escape_rejected` | PASSED | NOT RUN (skipped: Pillow not installed) |
| `Validator.test_signature_mismatch` | PASSED | NOT RUN (skipped: Pillow not installed) |

How the required test areas map to tests:

| Required area | Test(s) |
|---|---|
| Missing optional metadata | `MetadataParsing.test_missing_optional_fields_become_null`, `test_empty_strings_are_null_not_invented` |
| Public-domain eligibility | `Eligibility.test_public_domain_flag`, `test_rights_checked_before_image` |
| Empty/missing image URL | `Eligibility.test_empty_or_missing_image_url`, `test_unofficial_image_host` |
| HTTP error | `Http.test_404_not_retried`, `test_persistent_5xx_gives_up`, `test_503_honours_retry_after_then_succeeds`, `Downloads.test_http_error_on_image` |
| HTML instead of image | `Downloads.test_html_error_page_instead_of_image`, `test_html_body_with_image_content_type` |
| Truncated/invalid image | `Downloads.test_truncated_image`, `test_content_length_mismatch_is_truncation`, `test_garbage_bytes`, `Signature.*` |
| Duplicate SHA-256 | `Downloads.test_duplicate_sha256_rejected`, `Validator.test_duplicate_hash_across_records` |
| Manifest → missing file | `Validator.test_missing_local_file` |
| Hash mismatch | `Validator.test_hash_mismatch` |
| Invalid JSONL | `Validator.test_invalid_jsonl_line` |
| Existing-file protection | `FileSafety.test_existing_file_never_overwritten`, `test_collector_skips_record_whose_file_already_exists` |
| Safe filenames | `FileSafety.test_safe_filename`, `Validator.test_path_escape_rejected` |
| Source metadata vs. interpretation | `SourceVersusInterpretation.*` |
| No decoder ⇒ no pass | `Validator.test_no_decoder_means_no_pass` |

## 2. Live checks (real network, official hosts only)

| Check | Result | Evidence |
|---|---|---|
| GET `/public/collection/v1/objects/436121` | **BLOCKED** | `Tunnel connection failed: 403 Forbidden` (1 request, not retried) |
| GET `https://images.metmuseum.org/` (one request through the pipeline's client, in memory) | **BLOCKED** | `network_blocked: Tunnel connection failed: 403 Forbidden` |
| `collector.py` live run | **BLOCKED** | status `blocked`, 0 records, 0 images |
| `validate_collection.py` | **NOT RUN** (nothing to validate) | exit 3, `status=no_manifest` |
| 436121: valid JSON / `isPublicDomain` / host | **NOT RUN** | depends on the blocked API request |
| Download → signature → Pillow decode → SHA-256 → manifest | **NOT RUN** | depends on the blocked image host |
| Search for further eligible objects | **NOT RUN** | the collector stops after a policy denial instead of retrying |

```
$ python3 collector.py
2026-10-09T08:51:56+0000 INFO run 20261009T085156Z start mode=live seeds=[436121] terms=['poster', 'print', 'typography', 'textile', 'photograph'] max_images=10
2026-10-09T08:51:56+0000 ERROR object 436121 failed: network_blocked: Tunnel connection failed: 403 Forbidden (https://collectionapi.metmuseum.org/public/collection/v1/objects/436121)
2026-10-09T08:51:56+0000 INFO planned 0 search candidates
2026-10-09T08:51:56+0000 INFO run 20261009T085156Z end status=blocked downloaded=0
{"run_id": "20261009T085156Z", "status": "blocked", "downloaded": 0, "failures": 1, "report": "/home/user/se_new/visual-culture-pilot/visual_culture_archive/reports/COLLECTION_REPORT.md"}
[exit 1]
$ python3 validate_collection.py
status=no_manifest records=0 valid_images=0 decoder=- errors=0 warnings=0 -> /home/user/se_new/visual-culture-pilot/visual_culture_archive/reports/validation_result.json
[exit 3]
```

You reported that the Met API returns HTTP 200 on your machine. That was **not** observed from
this container, and none of the results above rely on it.

## 3. Image validation layers

| Layer | Tool | Equivalent to full decode? |
|---|---|---|
| Content-Type `image/*`, not HTML/XML/JSON | stdlib | no |
| Magic bytes + JPEG/PNG/GIF end marker (`signature_check`) | stdlib | **no**: a preliminary check only |
| `Image.verify()` + `Image.load()` | Pillow | yes (full decode) |

The validator never passes a record on the signature check alone. Without Pillow it emits
`image_decode_not_run`, and the record does not pass (see `Validator.test_no_decoder_means_no_pass`).

## Update: v1.1 search migration (2026-10-09)

The trigger was the Mac live run (user-reported output). Seed 436121 was saved and validated
(1 record, 1 valid image, Pillow 11.3.0, 0 errors). All five `v1/search` requests returned
HTTP 410. Search now uses `v1.1/search` with explicit `offset`/`limit` paging. The
10-image cap now counts records already in the manifest.

Mocked unit tests, re-run in the cloud container:

```
$ python3 -m unittest discover -s tests            # Python 3.13.16, Pillow 12.3.0
Ran 62 tests in 0.234s

OK

$ .venv/bin/python -m unittest discover -s tests   # Python 3.9.25, no Pillow
Ran 62 tests in 0.035s

OK (skipped=22)
```

These mocked tests do **not** show that live v1.1 search works. That needs a live run on the Mac.
