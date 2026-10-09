# Acceptance tests

Everything below runs **offline**, needs **no API keys**, and touches no real website.
Run from `visual_culture_platform/`. `$W` is any empty working directory, for example `W=$(mktemp -d)`.

## Level 1: automated tests

```bash
python3 tests/run_tests.py          # stdlib runner; expected last line: "78 passed, 0 failed in …"
python3 -m pytest -q                # if pytest is installed; expected: 78 passed
```

Pass condition: exit status 0 and zero failures. Without Pillow, two tests print that their
colour/brightness parts were skipped, and without jsonschema, the JSON Schema cross-check is
skipped. That is expected; both still count as passes.

## Level 2: scripted end-to-end run

```bash
bash scripts/acceptance.sh "$W"     # expected last line: "47 passed, 0 failed  (work dir: …)"; exit 0
```

| ID | Command (via `magref --data-dir $W/data --fixtures fixtures/web`) | Expected exit | Expected evidence |
|---|---|---|---|
| AT01 | `init` | 0 | `database ready: …/database/references.sqlite3 (schema v2)` |
| AT02 | `source import fixtures/sources.fixture.json` | 0 | 6 sources |
| AT03 | `source list` | 0 | `restricted-demo` listed as restricted, `disabled-demo` enabled=no |
| AT04 | `discover --source disabled-demo` | **4** | "is disabled" |
| AT05 | `discover --source restricted-demo` | **4** | "is restricted" |
| AT06 | `discover --source atelier` | **6** | pages found 11 (new 10, already known 1, filtered 1); `! http_404: …/sitemap-missing.xml` |
| AT07 | `crawl --source atelier` | **6** | fetched 7, new 5, blocked 2 (`robots_disallowed`, `http_403`), failed 1 (`http_404`), skipped 1 (noindex) |
| AT08 | `discover --source northlight` | 0 | 3 pages, 3 images (policy unknown) |
| AT09 | `discover --source open-archive` | 0 | images found 29 |
| AT10 | `policy-review --pending` | 0 | northlight/folio/disabled-demo awaiting review; 3 images unknown |
| AT11 | `download` (without `--approved`) | **2** | "pass --approved" |
| AT12 | `download --approved --limit 100` | **6** | downloaded 20, already stored (same SHA-256) 16, blocked 1 `host_not_allowed`, not eligible 3 |
| AT13 | `download --approved --limit 100` (re-run) | 0 | `selected 0`: nothing is downloaded twice, blocked items are not re-tried |
| AT14 | `verify --all` | 0 | `checked 20 file(s): ok 20, missing 0, corrupt 0` |
| AT15 | `deduplicate --dry-run` | 0 | shared files: 9; duplicate copies on disk: 0 |
| AT16 | `search --kind pages -q "large hero images generous whitespace asymmetric grid minimalist fashion"` | 0 | first hit "Quiet Volume…", with `why:` explanations and the source URL |
| AT17 | `search -q poster --years 1980-1984 --country JP` | 0 | only JP posters dated 1980–1984 |
| AT18/19 | `export --format json --kind pages/images -o …` | 0 | "(json, validated)" |
| AT20 | `validate $W/images.json` | 0 | `valid: 40 images record(s)` |
| AT21 | `analyze` | 0 | `36 measured` |
| AT22 | `trend compare --feature orientation --a 1980-1989 --b 2010-2019` | 0 | "In this collection (13 vs 12 assets …)" + limitations |
| AT23 | `trend compare … --a 1980-1981 --b 2010-2011` | 0 | "Insufficient sample … No trend is asserted." |
| AT24/25 | `research context-add …`, `research claim-add …` | 0 | context #1, claim #1 (unverified) |
| AT26 | `research claim-review --claim 1 --status verified --reviewer x` | **4** | "refused: cannot set 'verified': needs a source …" |
| AT27–29 | `project create …`, `project add-context …`, `project report … -o $W/report.md` | 0 | report with sections 1–9 |
| AT30 | `status` | 0 | counts and a "recent errors" list (404, 403, robots, jsonld, host_not_allowed) |
| AT31 | `show --id mi_00000000000000000000` | **3** | "not found" |
| AT32 | `ingest-html fixtures/local_html/saved_quiet_volume.html --source atelier` | 0 | `pages new 0, updated 1` (or new 1 on an empty DB), origin "saved-from comment", 1 local image copy not imported; no HTTP request |
| AT33 | `ingest-html fixtures/local_html --source atelier --links` | **6** | `wrong_site.html` and `not_html.html` fail with reasons; the report document adds same-site links and lists other hosts (`unknown-zine.test`, ...) |
| AT34 | `ingest-html fixtures/local_html --source restricted-demo` | **4** | refused: restricted source |

## Level 3: manual checks

**M1. Files are real and match the DB.** Under `$W/data/images/` the files are named
`<sha256>.png`. Running `sha256sum` on any of them returns its file name.
`magref --data-dir $W/data --json show --id <a downloaded mi_…>` shows the same `sha256` and an
absolute `local_path`.

**M2. Missing and corrupt detection.** Delete one file under `images/` and append a byte to
another. `verify --all` exits 6 and reports `missing 1, corrupt 1`. The corrupt file is moved to
`quarantine/corrupt/` (not deleted), and every record that points at either file becomes
`missing_file`. Then run `retry --failed --include-missing --limit 100`. The bytes are fetched
again and restored at their content-addressed paths, reported as "already stored (same SHA-256)",
and a new `verify --all` exits 0 with `missing 0, corrupt 0`.

**M3. Crash recovery.** This is covered by `test_crash_between_file_move_and_db_commit_is_repaired`.
To see it by hand, kill a `download` mid-run with `kill -9`. Afterwards `status` shows
"interrupted download(s): run `magref repair`" if a journal is left, and `repair` finishes the
work.

**M4. Blocked items wait for a policy change.** After AT12, `show --id` of the blocked
`cdn.unrelated.test` item shows `download_status: blocked` (`host_not_allowed`). A second
`download --approved` does not touch it (AT13). Re-record the source decision with
`policy-review --source open-archive --set allowed --license CC0-1.0 --evidence-url https://open-archive.test/terms.html --reviewer you`.
The item returns to `pending`, and the next `download --approved` blocks it again, because the
host is still not allowed. That is the expected result.

**M5. Web UI.** Run `magref --data-dir $W/data serve` and open `http://127.0.0.1:8765/`. Check:

- Dashboard shows counts per decade and genre, and the pending reviews.
- Explore with `years=1980-1989&country=JP` shows thumbnails.
- An asset from `northlight` shows "no local file (pending)" and rights `unknown`.
- Trend comparison with `a=1980-1981` shows the insufficient-sample notice.
- Context explorer shows the status badge and the "Not verified" notice.
- Design workspace: create a project, add a reference from an asset page, add a note, then
  Generate report. The page shows sections 1–9 and offers a Markdown download.

## Level 4: optional live check (only when outbound HTTPS is available)

Do this only with a source whose terms you have read yourself:

1. `source add …`
2. `policy-review --source … --set allowed --license … --evidence-url … --reviewer …`
3. `discover --source … --limit 5`
4. `crawl --source … --limit 5`
5. `download --approved --limit 3 --max-bytes 5000000`
6. `verify --all`

Expected: robots.txt is fetched first, requests are spaced by `MAGREF_REQUEST_INTERVAL`, and
any 403/429 shows up in `status` without bypass attempts.
**Claude has not performed this step;** no live source has been verified.
