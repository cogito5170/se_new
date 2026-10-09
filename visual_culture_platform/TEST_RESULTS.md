# Test results

> **Update 2026-10-09 (ingest-html added):** `python3 tests/run_tests.py` → **78 passed, 0 failed**
> (Python 3.13; adds `tests/test_ingest_html.py`, 5 tests). `bash scripts/acceptance.sh` →
> **47 passed, 0 failed** (adds AT32–AT34). The rest of this file is the earlier run of 73 tests and 42 checks.

Recorded by Claude in the development container on **2026-10-09**. This environment differs
from the target VM. Antigravity's own runs are the results that count for acceptance.

## Environment

| | |
|---|---|
| OS | Linux (cloud container) |
| Python | 3.13.16 (with Pillow 12.3.0 and jsonschema 4.26.0) and 3.11.17 (no Pillow, no jsonschema) |
| pytest | **not installed and not installable** (PyPI unreachable: DNS failure). The tests are written in pytest style, but they ran through the stdlib runner `tests/run_tests.py`. **pytest itself was not executed.** |
| Network | outbound web blocked (`curl https://www.w3.org/robots.txt` → `CONNECT tunnel failed, response 403`). **No real website was contacted.** |

## Automated tests: `python3 tests/run_tests.py`

| Interpreter | Result |
|---|---|
| Python 3.13.16 | **73 passed, 0 failed** (≈13.6 s) |
| Python 3.11.17 | **73 passed, 0 failed** (≈12.0 s). Two tests printed that their optional parts were skipped: colour/brightness measurement (no Pillow) and the jsonschema cross-check (no jsonschema). |

The repository-level wrapper `python3 tests/test_visual_culture_platform.py`, which `scripts/tests.sh`
and CI pick up, ran the same suite and reported `73 passed, 0 failed -- 통과`.

**The tests can fail.** Four deliberate breakages were each made in a throwaway copy of the code
and caught:

| Breakage introduced | Test that failed |
|---|---|
| policy gate removed from download selection | `test_unknown_policy_source_keeps_metadata_but_downloads_nothing` |
| SSRF URL check removed from redirect hops | `test_redirects_followed_bounded_and_rechecked` |
| "verified needs a read supporting source" rule removed | `test_claims_never_auto_verify` (SQLite trigger backstop) |
| truncated-image end-marker check removed | `test_failure_modes_are_classified_and_leave_no_temp_files` |

<details><summary>Per-test list (Python 3.13)</summary>

```
PASS  test_cli_web_logging::test_cli_end_to_end_with_exit_codes
PASS  test_cli_web_logging::test_logs_redact_secrets_and_home_paths
PASS  test_cli_web_logging::test_web_ui_screens_and_safety
PASS  test_config::test_env_example_parses_with_inline_comments
PASS  test_config::test_invalid_values_are_rejected
PASS  test_config::test_precedence_and_aliases
PASS  test_db_registry::test_constraints_reject_bad_rows
PASS  test_db_registry::test_schema_initialization_is_idempotent
PASS  test_db_registry::test_source_validation_and_policy_reviews
PASS  test_download::test_429_with_retry_after_then_success_and_500_exhausted
PASS  test_download::test_blocked_items_are_not_retried_until_policy_changes
PASS  test_download::test_byte_budget_stops_the_run
PASS  test_download::test_crash_between_file_move_and_db_commit_is_repaired
PASS  test_download::test_failure_modes_are_classified_and_leave_no_temp_files
PASS  test_download::test_loopback_is_blocked_without_the_test_flag
PASS  test_download::test_missing_and_corrupt_files_are_detected_and_recoverable
PASS  test_download::test_normal_download_is_stored_verified_and_content_addressed
PASS  test_download::test_policy_gate_unknown_restricted_disabled
PASS  test_download::test_redirects_to_private_ip_or_foreign_host_are_blocked
PASS  test_download::test_same_bytes_from_two_urls_and_two_sources_stored_once
PASS  test_download::test_state_transitions_and_path_safety
PASS  test_extract::test_feature_evidence_levels_are_honest
PASS  test_extract::test_image_type_classification_separates_declared_from_inferred
PASS  test_extract::test_images_alt_caption_roles_and_tracking_pixel
PASS  test_extract::test_jsonld_graph_takes_precedence_and_provenance_is_recorded
PASS  test_extract::test_malformed_html_does_not_crash
PASS  test_extract::test_malformed_jsonld_and_bad_date_are_warnings_not_failures
PASS  test_extract::test_missing_metadata_stays_null
PASS  test_extract::test_open_graph_and_meta_fallbacks
PASS  test_extract::test_srcset_data_uri_language_and_robots_meta
PASS  test_http::test_403_and_404_are_not_retried
PASS  test_http::test_429_honours_retry_after_then_succeeds
PASS  test_http::test_hop_check_policy_applies_after_redirect
PASS  test_http::test_redirects_followed_bounded_and_rechecked
PASS  test_http::test_response_size_limit
PASS  test_http::test_retries_are_bounded_and_classified_transient
PASS  test_http::test_retry_after_longer_than_cap_gives_up
PASS  test_http::test_retry_classification
PASS  test_http::test_robots_404_allows_and_5xx_disallows
PASS  test_http::test_robots_disallow_and_crawl_delay
PASS  test_http::test_timeouts_retry_then_fail
PASS  test_netsafe::test_allow_loopback_is_only_loopback
PASS  test_netsafe::test_blocks_local_private_linklocal_and_metadata
PASS  test_netsafe::test_dns_answers_are_checked_all_of_them
PASS  test_netsafe::test_dns_failure_is_reported
PASS  test_netsafe::test_scheme_credentials_and_ports
PASS  test_pipeline_fixtures::test_catalog_years_are_never_invented
PASS  test_pipeline_fixtures::test_crawl_outcomes_and_canonical_dedup
PASS  test_pipeline_fixtures::test_fixture_downloads_dedup_and_host_policy
PASS  test_pipeline_fixtures::test_malformed_and_hostile_xml_rejected
PASS  test_pipeline_fixtures::test_rss_and_html_discovery
PASS  test_pipeline_fixtures::test_sitemap_discovery_dedup_filter_and_error_recording
PASS  test_pipeline_fixtures::test_unknown_policy_source_keeps_metadata_but_downloads_nothing
PASS  test_research::test_asset_metadata_roundtrip_and_many_genres
PASS  test_research::test_claims_never_auto_verify
PASS  test_research::test_context_relations_follow_evidence
PASS  test_research::test_design_project_roundtrip_and_report
PASS  test_research::test_feature_kinds_and_review
PASS  test_research::test_measurements_trends_and_small_samples
PASS  test_research::test_unknown_years_stay_unknown
PASS  test_search_export::test_exports_validate_and_round_trip
PASS  test_search_export::test_image_search_filters_year_region_genre_feature
PASS  test_search_export::test_invalid_documents_are_rejected_with_reasons
PASS  test_search_export::test_page_search_returns_source_backed_ranked_results
PASS  test_search_export::test_ranking_weights_and_coverage
PASS  test_search_export::test_schema_file_matches_generated_schema_and_jsonschema_crosscheck
PASS  test_search_export::test_tokenizer_is_light_and_deterministic
PASS  test_urls::test_normalization_rules
PASS  test_urls::test_redact_url_hides_credentials
PASS  test_urls::test_relative_resolution_and_invalid_schemes
PASS  test_urls::test_stable_ids_and_same_site
PASS  test_urls::test_tracking_parameters_removed_but_others_kept
PASS  test_urls::test_trailing_slash_is_significant_and_percent_encoding_normalized
73 passed, 0 failed
```
</details>

## Acceptance script: `bash scripts/acceptance.sh`

Run on Python 3.13 with no package installed (PYTHONPATH mode): **42 passed, 0 failed** (AT01–AT31).
The last run's state:

| What | Count |
|---|---|
| sources | 6 (2 allowed, 1 review_required, 2 unknown of which 1 disabled, 1 restricted) |
| discovered page URLs | 13: fetched 6, blocked 2 (robots.txt + HTTP 403), failed 1 (HTTP 404), skipped 1 (noindex), pending 3 (unknown-policy RSS source, not crawled by the script) |
| page references | 5 |
| image records | 40: downloaded 36, blocked 1 (host not allowed), pending 3 (policy unknown, never fetched) |
| files on disk | **20 distinct files** (2,355 bytes), each verified by SHA-256; 9 files are shared by more than one record |
| thumbnails | 20 (Pillow present) |

## What these numbers mean, and what they don't

- **Images were really downloaded and stored, but only from local fixtures.** All the bytes came
  from `fixtures/web/` (`FixtureTransport`) or from a local `http.server` on 127.0.0.1 (download
  tests). The streaming, SSRF pinning and redirect code ran against that local server over real
  sockets. It has **never** run against an internet host.
- **The fixture images are synthetic** (generated stripes and solid colours). They are good for
  checking hashing, dedup and integrity. Trend results computed from them (for example "light 0% → 100%")
  are artefacts of how the fixtures were built and **say nothing about real design history**.
- The contexts, claims and sources created in the tests and the acceptance run are fictional
  placeholders, labelled "SYNTHETIC" or "fictional".

## Not verified here

- Any real website, API, robots.txt or terms page.
- `pip install -e .`: building the package needs setuptools from PyPI, which was unreachable.
  `pip install --no-build-isolation --no-deps -e .` into a venv with system site-packages **did**
  succeed, and `magref --version` printed `magref 0.1.0`.
- pytest itself (see above).
- The web UI in a real browser. Every screen was requested over HTTP and its HTML checked by the
  tests; nobody looked at the rendering.
