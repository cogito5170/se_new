# Source and rights policy

## Principles

1. **Being able to access a URL is not permission.** A public URL, a robots.txt `Allow`, or an
   open directory says nothing about copyright, licence or terms of use.
2. **Only `allowed` downloads.** `allowed` is set by a person, and only with recorded evidence:
   a licence identifier and/or an evidence URL such as a terms page, a licence page or an API
   policy. All other statuses (`unknown`, `review_required`, `restricted`) keep files off disk.
3. **When unsure, keep metadata only.** For `unknown` and `review_required` sources the tool may
   record URLs and page metadata, marked as pending review. It never stores the image files.
4. **Never bypass.** No logins, cookies, paywall workarounds, CAPTCHA solving, user-agent spoofing
   or search-engine scraping. HTTP 401/403 is treated as `blocked` and not retried.
5. **Provenance for everything.** Each record keeps:
   - the source and discovery path
   - the original URL, the final URL and the page URL
   - the policy scope (source- or image-level), licence and evidence URL
   - the reviewer and the time of the decision

## Order in which to look for material

1. Official APIs and open datasets (`json_catalog` adapter + field mapping)
2. Open digital archives of museums, libraries and public institutions
3. Official publisher and artist websites (`sitemap`, `rss`, `html`)
4. Image repositories whose terms of use have been checked
5. Other providers that explicitly permit collection

## What the program enforces

| Rule | Where |
|---|---|
| robots.txt checked on every hop. 4xx means no robots file (allowed); 5xx or unreachable means disallow all (RFC 9309). | `http.Fetcher.robots_status` |
| robots.txt never changes the policy status; it is recorded separately (`robots_status`, `robots_note`) | `registry.py` |
| Crawl-delay honoured; per-host minimum interval; bounded concurrency | `http.RateLimiter`, `MAGREF_*` settings |
| `noindex` / `nofollow` meta respected | `pages.py`, `discovery.py` |
| Disabled or `restricted` source: discovery, crawl and download refused (exit code 4) | `cli.usable_source`, `downloader` |
| Image downloads only for effective policy `allowed`, from the source's own host or `allowed_asset_hosts`, checked again after every redirect | `downloader.py` |
| Per-file size cap, per-run file count and byte budget, page size cap | settings |
| No credentials sent; credential-looking query values and `Authorization` / `Cookie` masked in logs; home directory path masked | `logutil.py` |
| SSRF guards: http/https only, no URL credentials, no localhost / private / link-local / metadata / reserved addresses (literal or via DNS), standard ports only, at most 5 redirects, connection pinned to the vetted IP | `netsafe.py`, `http.SafeTransport` |
| A SHA-256 match is treated as byte identity only, never as evidence of licence or ownership | `maintenance.deduplicate` note, docs |

## Recording a decision

```bash
magref policy-review --pending
magref policy-review --source my-museum --set allowed \
    --license CC0-1.0 --evidence-url https://museum.example/open-access-policy \
    --terms-url https://museum.example/terms --robots-note "robots allows /collection" \
    --note "Open Access images only; credit line requested" --reviewer "your name"
magref policy-review --image mi_... --set restricted --note "credit says 'all rights reserved'" --reviewer "your name"
magref policy-review --history
```

A later review replaces the effective status. Every review stays in `policy_reviews`.
Changing a policy or a source's configuration makes its `blocked` images eligible again; nothing
else does.

## Historical claims

Interpretations are kept apart from observations:

- Context records and claims start `unverified`.
- `verified` requires a source that **supports** the claim and was actually read (excerpt or full
  text). A search-result title or an abstract alone is not enough, and the code refuses it.
- Sharing a period with an event (`same_period`) is not influence. `documented_influence` requires
  a verified claim.
- Trend outputs describe **this collection only**. They show sample sizes, source distribution and
  missing data, and assert nothing below the minimum sample (default 10).
