#!/usr/bin/env bash
# Offline end-to-end acceptance run over the fixture web (no network, no API keys).
#
#   bash scripts/acceptance.sh [WORK_DIR]
#
# Uses `magref` if installed, otherwise `python3 -m magref` with PYTHONPATH=src.
# Every step checks its exit code against the expected one and prints PASS/FAIL.
# Exit status: 0 if every check passed, 1 otherwise.
# (Variable names are ASCII only: bash does not accept other identifiers.)
set -u

here="$(cd "$(dirname "$0")/.." && pwd)"
work="${1:-$(mktemp -d)}"
data="$work/data"
fixtures="$here/fixtures/web"
export MAGREF_LOG_LEVEL=WARNING

if command -v magref >/dev/null 2>&1; then
    runner=(magref)
else
    export PYTHONPATH="$here/src${PYTHONPATH:+:$PYTHONPATH}"
    runner=(python3 -m magref)
fi
mr() { "${runner[@]}" --data-dir "$data" --fixtures "$fixtures" "$@"; }

pass=0
fail=0
check() {   # check NAME EXPECTED_EXIT -- command...
    local name="$1" expected="$2"
    shift 3
    local out code
    out="$("$@" 2>&1)"
    code=$?
    if [ "$code" -eq "$expected" ]; then
        pass=$((pass + 1))
        printf 'PASS  %-58s exit=%s\n' "$name" "$code"
    else
        fail=$((fail + 1))
        printf 'FAIL  %-58s exit=%s expected=%s\n' "$name" "$code" "$expected"
        printf '%s\n' "$out" | tail -15 | sed 's/^/      /'
    fi
    last_out="$out"
}
contains() {   # contains NAME NEEDLE  (checks the previous step's output)
    if printf '%s' "$last_out" | grep -qF -- "$2"; then
        pass=$((pass + 1)); printf 'PASS  %-58s\n' "$1"
    else
        fail=$((fail + 1)); printf 'FAIL  %-58s (missing: %s)\n' "$1" "$2"
    fi
}

echo "work dir: $work"
check "AT01 init database"                        0 -- mr init
check "AT02 import fixture sources"               0 -- mr source import "$here/fixtures/sources.fixture.json"
check "AT03 list sources"                         0 -- mr source list
contains "AT03 restricted source listed"          "restricted-demo"
check "AT04 disabled source refused"              4 -- mr discover --source disabled-demo
check "AT05 restricted source refused"            4 -- mr discover --source restricted-demo
check "AT06 discover sitemap (one 404 recorded)"  6 -- mr discover --source atelier
contains "AT06 missing sitemap reported"          "http_404"
check "AT07 crawl pages (robots/403/404 recorded)" 6 -- mr crawl --source atelier
contains "AT07 robots disallow reported"          "robots_disallowed"
check "AT08 discover RSS (policy unknown)"        0 -- mr discover --source northlight
check "AT09 discover JSON catalog"                0 -- mr discover --source open-archive
check "AT10 policy review lists pending items"    0 -- mr policy-review --pending
contains "AT10 northlight awaiting review"        "northlight"
check "AT11 download requires --approved"         2 -- mr download
check "AT12 download approved (1 host blocked)"   6 -- mr download --approved --limit 100
contains "AT12 dedup by SHA-256 reported"         "already stored (same SHA-256)"
check "AT13 re-run downloads nothing new"         0 -- mr download --approved --limit 100
contains "AT13 nothing selected"                  "selected 0"
check "AT14 verify files"                         0 -- mr verify --all
contains "AT14 no missing files"                  "missing 0"
check "AT15 deduplicate dry-run"                  0 -- mr deduplicate --dry-run
check "AT16 keyword search pages"                 0 -- mr search --kind pages -q "large hero images generous whitespace asymmetric grid minimalist fashion"
contains "AT16 top hit is the minimalist story"   "Quiet Volume"
check "AT17 search images by years+country"       0 -- mr search -q poster --years 1980-1984 --country JP
check "AT18 export pages (validated)"             0 -- mr export --format json --kind pages -o "$work/pages.json"
check "AT19 export images (validated)"            0 -- mr export --format json --kind images -o "$work/images.json"
check "AT20 validate export file"                 0 -- mr validate "$work/images.json"
check "AT21 measure stored images"                0 -- mr analyze
check "AT22 compare periods (sufficient sample)"  0 -- mr trend compare --feature orientation --a 1980-1989 --b 2010-2019
contains "AT22 descriptive statement"             "In this collection"
check "AT23 small sample -> no trend asserted"    0 -- mr trend compare --feature orientation --a 1980-1981 --b 2010-2011
contains "AT23 insufficient sample stated"        "No trend is asserted"
check "AT24 add context record"                   0 -- mr research context-add --title "Fictional poster festival" --description "SYNTHETIC test context" --type exhibition_event --start 1983 --end 1987 --country JP
check "AT25 add claim"                            0 -- mr research claim-add --text "Fictional claim" --type influence --context 1
check "AT26 verify without evidence refused"      4 -- mr research claim-review --claim 1 --status verified --reviewer acceptance
check "AT27 create design project"                0 -- mr project create --title "Acceptance project" --brief "Poster series" --medium print
check "AT28 link context to project"              0 -- mr project add-context --project 1 --context 1
check "AT29 generate report"                      0 -- mr project report --project 1 --format markdown -o "$work/report.md"
check "AT30 status"                               0 -- mr status
contains "AT30 recent errors section"             "recent errors"
check "AT31 unknown id -> not found"              3 -- mr show --id mi_00000000000000000000

echo
echo "$pass passed, $fail failed  (work dir: $work)"
[ "$fail" -eq 0 ]
