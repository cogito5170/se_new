# Visual Culture Research Platform (`magref`)

A local tool for finding, collecting, organising and studying visual-culture
references, including magazine covers and spreads, editorial and fashion
photography, posters and advertising. It links them to **sourced** historical
context and to design-planning projects.

It covers three specifications that build on each other:

| Spec | Scope | Where |
|---|---|---|
| Magazine Reference Discovery & Retrieval | sources, discovery, page metadata, design-feature evidence, keyword search, JSON export | `discovery.py`, `pages.py`, `extract.py`, `features.py`, `search.py`, `export.py` |
| Magazine Reference Image Collector | policy review, SSRF-safe streaming downloads, SHA-256 storage/dedup, verify/repair | `registry.py`, `netsafe.py`, `http.py`, `downloader.py`, `storage.py`, `maintenance.py` |
| Visual Culture Research Platform | genres, measured vs semantic features, context records, sources and claims, trends, design projects, web UI | `research.py`, `analysis.py`, `trends.py`, `projects.py`, `web.py` |

**Status in one line:** it runs offline against bundled synthetic fixtures. 73 automated tests and
42 acceptance checks pass in this environment. **No real website has been contacted:** outbound
web access was blocked here. See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) and [TEST_RESULTS.md](TEST_RESULTS.md).

## Install

Python **3.11+**. The core has **no third-party runtime dependencies** (stdlib only).

```bash
cd visual_culture_platform
python3 -m venv .venv && . .venv/bin/activate
pip install -e .                 # needs PyPI access to fetch setuptools (build backend)
pip install -e ".[images,dev]"   # optional: Pillow (colour/brightness), pytest, jsonschema
magref --version
```

Without network access to PyPI, run directly from the source tree instead. Nothing needs installing:

```bash
cd visual_culture_platform
export PYTHONPATH=$PWD/src
python3 -m magref --version
```

## Quick start (offline, bundled fixtures)

```bash
bash scripts/acceptance.sh /tmp/magref-acceptance     # 42 checks, prints PASS/FAIL per step
python3 tests/run_tests.py                            # unit/integration tests without pytest
python3 -m pytest -q                                  # same tests with pytest, if installed
```

Doing the same flow by hand (`--fixtures` serves every HTTP request from `fixtures/web/`):

```bash
M="magref --data-dir /tmp/vc-demo --fixtures fixtures/web"
$M init
$M source import fixtures/sources.fixture.json
$M discover --source open-archive          # JSON catalog -> image candidates with year/country/genre
$M policy-review --pending                 # what still needs a rights decision
$M download --approved --limit 50          # only items whose policy is 'allowed'
$M verify --all                            # files vs database (missing / corrupt / orphans)
$M analyze                                 # measured features from the stored bytes
$M search -q poster --years 1980-1989 --country JP
$M trend compare --feature orientation --a 1980-1989 --b 2010-2019
$M discover --source atelier && $M crawl --source atelier
$M search --kind pages -q "large hero images generous whitespace asymmetric grid minimalist fashion"
$M export --format json --kind images -o /tmp/vc-demo/exports/images.json
$M serve                                   # web UI on http://127.0.0.1:8765/
```

## Using it with real sources

1. Register the source with `magref source add --id ... --name ... --base-url ... --method sitemap|rss|html|json_catalog`,
   or import a JSON file shaped like `fixtures/sources.fixture.json`.
2. Read the site's terms, licence and API policy. Then record a decision **with evidence**:
   `magref policy-review --source ID --set allowed --license CC0-1.0 --evidence-url https://.../terms --reviewer NAME`.
   Until then the policy is `unknown`: metadata may be collected, but **no image file is downloaded**.
3. `discover` → `crawl` (pages) → `download --approved` → `verify --all` → `analyze`.
4. Set `MAGREF_USER_AGENT` to something that identifies you. See [SOURCE_POLICY.md](SOURCE_POLICY.md).

## Commands

| Area | Commands |
|---|---|
| setup | `init`, `status`, `schema` |
| sources & rights | `source list/add/show/enable/disable/import`, `policy-review --pending/--history/--source X --set S/--image ID --set S` |
| collection | `discover --source`, `crawl --source [--retry-failed]`, `download --approved [--limit --max-bytes --source --id]`, `retry --failed [--include-missing]`, `reset --id` |
| integrity | `verify --all [--orphans --relocate]`, `repair`, `deduplicate [--dry-run / --apply]`, `clean-temp` |
| retrieval | `search -q ... [--kind images/pages] [--years --country --region --genre --feature type=value --image-type --source ...]`, `show --id`, `export`, `import`, `validate` |
| research | `analyze`, `asset set/genre`, `genre list/add`, `feature add/review/list`, `research source-add/claim-add/claim-link/claim-review/context-add/context-review/relate/...` |
| trends | `trend compare/frequency/emergence/common/timeline` |
| planning | `project create/list/show/add-asset/add-context/add-feature/note/report`, `serve` |

`magref <command> --help` documents every flag. Add `--json` before the command for machine-readable output.

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | ok |
| 1 | operational failure |
| 2 | usage/config error |
| 3 | not found |
| 4 | refused by policy or a trust rule |
| 5 | validation failure |
| 6 | completed with errors (some items failed; see `magref status`) |

## Configuration

Set environment variables or use a `.env` file (see [.env.example](.env.example)). The data root is
`VC_ARCHIVE_DIR` (alias `MAGREF_DATA_DIR`) and defaults to `~/visual_culture_archive`:

```
images/<publisher_slug>/<YYYY>/<sha256[:2]>/<sha256>.<ext>   thumbnails/   database/references.sqlite3
manifests/pending/ (download journal)   exports/   logs/magref.log   tmp/   quarantine/
```

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): components and data flow
- [DATA_MODEL.md](DATA_MODEL.md): tables, relations, enums and the JSON contracts
- [SOURCE_POLICY.md](SOURCE_POLICY.md): collection and rights policy
- [HANDOFF.md](HANDOFF.md): transfer contract for the Antigravity execution agent
- [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md): acceptance procedure
- [TEST_RESULTS.md](TEST_RESULTS.md): actual results
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md): limitations and what is not implemented
