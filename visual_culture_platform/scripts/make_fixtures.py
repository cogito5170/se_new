#!/usr/bin/env python3
"""Regenerate the offline fixture web under fixtures/web/ (deterministic).

All hosts use the reserved `.test` TLD (RFC 2606) and all content is SYNTHETIC:
invented publications, invented works, generated solid/gradient images. Nothing
here describes a real publisher, artist or historical fact.

    python3 scripts/make_fixtures.py          # rewrites fixtures/web and fixtures/sources.fixture.json

Images are written with a tiny pure-Python PNG encoder; the single JPEG fixture
is a hand-assembled baseline header + Pillow body when Pillow is present
(otherwise a pre-made JPEG is kept as is).
"""
from __future__ import annotations

import json
import random
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "fixtures"
WEB = ROOT / "web"


def png(width: int, height: int, pixel) -> bytes:
    """pixel(x, y) -> (r, g, b). Pure-Python PNG (8-bit RGB, no interlace)."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel(x, y))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def solid(rgb):
    return lambda x, y: rgb


def split(rgb_a, rgb_b, vertical=True, share_a=4):
    """Stripes of period 8 px; `share_a` of every 8 px use rgb_a."""
    def f(x, y):
        return rgb_a if (x if vertical else y) % 8 < share_a else rgb_b
    return f


def write(rel: str, data: bytes | str) -> None:
    path = WEB / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    path.write_bytes(data)


def page(title, body, head="", lang="en") -> str:
    return (f"<!DOCTYPE html>\n<html lang=\"{lang}\"><head><meta charset=\"utf-8\">\n"
            f"<title>{title}</title>\n{head}</head>\n<body>\n{body}\n</body></html>\n")


def atelier() -> None:
    h = "atelier-journal.test"
    write(f"{h}/robots.txt", "User-agent: *\nDisallow: /private/\n\nSitemap: https://atelier-journal.test/sitemap.xml\n")
    write(f"{h}/sitemap.xml", """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://atelier-journal.test/sitemap-articles.xml</loc></sitemap>
  <sitemap><loc>https://atelier-journal.test/sitemap-missing.xml</loc></sitemap>
</sitemapindex>
""")
    urls = ["/stories/quiet-volume.html", "/stories/quiet-volume.html?utm_source=newsletter&utm_medium=email",
            "/stories/quiet-volume-amp.html", "/stories/serif-season.html", "/stories/gallery-blue-hour.html",
            "/stories/bare-page.html", "/stories/broken-jsonld.html", "/stories/noindex.html",
            "/stories/gone.html", "/stories/forbidden.html", "/private/draft.html",
            "https://elsewhere.test/not-ours.html"]
    entries = []
    for u in urls:
        loc = u if u.startswith("http") else f"https://atelier-journal.test{u}"
        loc = loc.replace("&", "&amp;")
        extra = ""
        if u == "/stories/quiet-volume.html":
            extra = ("<image:image><image:loc>https://atelier-journal.test/media/quiet-volume-hero.png</image:loc>"
                     "<image:title>Quiet Volume cover</image:title></image:image>")
        entries.append(f"  <url><loc>{loc}</loc>{extra}</url>")
    write(f"{h}/sitemap-articles.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n' + "\n".join(entries) + "\n</urlset>\n")
    write(f"{h}/terms.html", page("Terms -- Atelier Journal (fixture)",
          "<h1>Terms</h1><p>SYNTHETIC FIXTURE. All text and images on atelier-journal.test were generated "
          "for automated tests and may be downloaded and reused freely (CC0-1.0).</p>"))

    jsonld = json.dumps({"@context": "https://schema.org", "@graph": [
        {"@type": "NewsArticle", "headline": "Quiet Volume: a minimalist fashion editorial",
         "description": "Large hero images, generous whitespace and an asymmetric grid with restrained typography.",
         "datePublished": "2026-03-02T09:30:00+09:00", "dateModified": "2026-03-04",
         "inLanguage": "en", "articleSection": "Fashion",
         "keywords": ["minimal", "editorial", "whitespace", "asymmetric grid", "fashion"],
         "author": [{"@type": "Person", "name": "Mina Park (fictional)"}],
         "publisher": {"@type": "Organization", "name": "Atelier Journal"},
         "image": {"@type": "ImageObject", "url": "https://atelier-journal.test/media/quiet-volume-hero.png",
                   "width": 60, "height": 40},
         "isAccessibleForFree": True},
        {"@type": "WebSite", "name": "Atelier Journal"}]})
    head = (f'<link rel="canonical" href="https://atelier-journal.test/stories/quiet-volume.html">\n'
            f'<meta property="og:title" content="Quiet Volume (OG title)">\n'
            f'<meta property="og:site_name" content="Atelier Journal">\n'
            f'<meta property="og:image" content="/media/quiet-volume-hero.png">\n'
            f'<meta property="og:image:alt" content="Model in an oversized white coat, magazine cover">\n'
            f'<meta name="theme-color" content="#f4f1ea">\n'
            f'<style>body{{font-family: "Canela", Georgia, serif}} .dek{{font-family: "Neue Haas Grotesk", Helvetica, sans-serif}}</style>\n'
            f'<script type="application/ld+json">{jsonld}</script>\n')
    body = ('<article class="layout-asym grid-12">\n'
            '<figure class="hero"><img src="/media/quiet-volume-hero.png" alt="Model in an oversized white coat, magazine cover" width="60" height="40">'
            '<figcaption>Cover story, photographed against a bare plaster wall.</figcaption></figure>\n'
            '<h1>Quiet Volume</h1><p class="dek">Restraint as a design decision.</p>\n'
            '<p>The issue opens with a single image and a lot of air. Columns are offset; the text block '
            'sits low and to the right.</p>\n'
            '<blockquote>Leave the page room to breathe.</blockquote>\n'
            '<figure><img src="/media/quiet-volume-spread.png" alt="Interior spread with offset columns" width="80" height="40">'
            '<figcaption>Interior spread.</figcaption></figure>\n'
            '<h2>Making space</h2><p>Typography stays small and quiet so the photographs carry the page.</p>\n'
            '<img src="/media/pixel.gif" width="1" height="1" alt="">\n'
            '</article>')
    write(f"{h}/stories/quiet-volume.html", page("Quiet Volume | Atelier Journal", body, head))
    # Alternate URL of the same article (canonical points to the original).
    write(f"{h}/stories/quiet-volume-amp.html", page("Quiet Volume (AMP)", "<article><h1>Quiet Volume</h1>"
          "<p>Alternate rendering.</p></article>",
          '<link rel="canonical" href="https://atelier-journal.test/stories/quiet-volume.html?utm_campaign=amp">\n'))
    serif = ("<article><h1>Serif Season</h1>"
             + "".join(f"<h2>Part {i}</h2><p>" + ("Long-form essay text about book faces and editorial "
                       "typography in print magazines. " * 30) + "</p>" for i in range(1, 4))
             + '<figure><img src="/media/serif-cover.png" alt="Typographic magazine cover with a large serif masthead">'
             "<figcaption>Cover.</figcaption></figure></article>")
    write(f"{h}/stories/serif-season.html", page("Serif Season", serif,
          '<meta name="description" content="A long read on serif typography in editorial design.">\n'
          '<meta property="og:type" content="article">\n<meta property="article:section" content="Typography">\n'
          '<meta property="article:tag" content="typography, serif, long-form">\n'
          '<meta property="article:published_time" content="2025-11-20">\n'
          '<meta name="author" content="J. Doe (fictional)">\n'
          '<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700&family=Inter" rel="stylesheet">\n'))
    gallery = ('<article><h1>Blue Hour</h1>'
               + "".join(f'<figure><img src="/media/blue-hour-{i}.png" alt="Blue hour editorial photo {i}"></figure>'
                         for i in range(1, 6))
               + "<p>Five frames at dusk.</p></article>")
    write(f"{h}/stories/gallery-blue-hour.html", page("Blue Hour", gallery,
          '<script type="application/ld+json">{"@context":"https://schema.org","@type":"ImageGallery",'
          '"name":"Blue Hour","description":"Photo essay at dusk","datePublished":"2024-06-01"}</script>\n'))
    write(f"{h}/stories/bare-page.html", "<html><head><title>Untitled note</title></head><body><p>Short note.</p></body></html>")
    write(f"{h}/stories/broken-jsonld.html", page("Broken metadata",
          "<article><h1>Broken metadata</h1><p>This page has a malformed JSON-LD block.</p></article>",
          '<script type="application/ld+json">{"@type": "Article", "headline": "Broken", </script>\n'
          '<meta property="article:published_time" content="not-a-date">\n'))
    write(f"{h}/stories/noindex.html", page("Private preview", "<p>Preview</p>",
          '<meta name="robots" content="noindex, nofollow">\n'))
    write(f"{h}/private/draft.html", page("Draft", "<p>Robots-disallowed draft.</p>"))

    random.seed(7)
    hero = png(60, 40, split((244, 241, 234), (230, 226, 218)))
    write(f"{h}/media/quiet-volume-hero.png", hero)
    write(f"{h}/media/hero-copy.png", hero)        # identical bytes, different URL
    write(f"{h}/media/quiet-volume-spread.png", png(80, 40, split((250, 250, 248), (40, 40, 40))))
    write(f"{h}/media/serif-cover.png", png(40, 60, split((120, 20, 30), (245, 235, 220), vertical=False)))
    for i in range(1, 6):
        write(f"{h}/media/blue-hour-{i}.png", png(48, 32, solid((20 + i * 5, 40 + i * 6, 120 + i * 10))))
    write(f"{h}/media/pixel.gif", b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00"
          b"\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")
    write(f"{h}/_fixture.json", json.dumps({
        "/stories/forbidden.html": {"status": 403, "body": "<h1>Forbidden</h1>"},
        "/media/fake.jpg": {"status": 200, "headers": {"Content-Type": "image/jpeg"},
                            "body": "<!DOCTYPE html><html><body>Not found</body></html>"},
        "/media/moved-hero.png": {"status": 301, "headers": {"Location": "/media/quiet-volume-hero.png"}},
        "/media/to-metadata.png": {"status": 302, "headers": {"Location": "http://169.254.169.254/latest/meta-data/"}},
        "/media/rate-limited.png": {"status": 429, "headers": {"Retry-After": "1"}},
    }, indent=2))


def northlight() -> None:
    h = "northlight-mag.test"
    items = []
    for i, (slug, title) in enumerate([("neon-type", "Neon Type"), ("paper-cuts", "Paper Cuts"),
                                       ("studio-light", "Studio Light")], 1):
        items.append(f"""  <item><title>{title}</title><link>https://northlight-mag.test/features/{slug}.html</link>
    <pubDate>Mon, 0{i} Sep 2025 10:00:00 +0000</pubDate>
    <enclosure url="https://northlight-mag.test/img/{slug}.png" type="image/png" length="100"/></item>""")
        write(f"{h}/features/{slug}.html", page(f"{title} | Northlight", f"<article><h1>{title}</h1>"
              f'<img src="/img/{slug}.png" alt="{title} poster"><p>Feature text.</p></article>',
              '<meta property="og:site_name" content="Northlight">\n'))
        write(f"{h}/img/{slug}.png", png(32, 48, solid((200 - i * 40, 30 * i, 90))))
    write(f"{h}/feed.xml", '<?xml version="1.0"?>\n<rss version="2.0"><channel><title>Northlight (fixture)</title>\n'
          + "\n".join(items) + "\n</channel></rss>\n")


def folio() -> None:
    h = "folio-review.test"
    write(f"{h}/index.html", page("Folio Review", """<h1>Folio Review</h1>
<ul>
<li><a href="/reviews/layout-notes.html">Layout notes</a></li>
<li><a href="reviews/grid-study.html?utm_source=home">Grid study</a></li>
<li><a href="/reviews/layout-notes.html#comments">Layout notes (fragment)</a></li>
<li><a href="https://other-site.test/page.html">External</a></li>
<li><a href="/reviews/sponsored.html" rel="nofollow sponsored">Sponsored</a></li>
<li><a href="/files/catalogue.pdf">PDF</a></li>
<li><a href="mailto:editor@folio-review.test">Mail</a></li>
</ul>"""))
    write(f"{h}/reviews/layout-notes.html", page("Layout notes", "<article><h1>Layout notes</h1><p>Notes.</p></article>"))
    write(f"{h}/reviews/grid-study.html", page("Grid study", "<article><h1>Grid study</h1><p>Study.</p></article>"))


ARCHIVE_ITEMS = []


def archive() -> None:
    """Synthetic museum-style JSON catalog with dated, genred works (for research features)."""
    h = "open-archive.test"
    rnd = random.Random(42)
    items = []
    n = 0
    # 1980s: mostly saturated warm, high contrast posters (synthetic)
    for i in range(12):
        n += 1
        warm = [(220, 40, 30), (240, 120, 20), (230, 200, 30)][i % 3]
        dark = (15, 15, 20)
        img = png(40, 56, split(warm, dark, vertical=bool(i % 2), share_a=6))
        write(f"{h}/media/work-{n:03d}.png", img)
        items.append({"id": f"OA-{n:03d}", "title": f"Synthetic poster study {n}",
                      "creator": f"Fictional Studio {i % 4 + 1}", "date": None, "year": 1980 + i % 10,
                      "country": "KR" if i % 2 else "JP", "region": "East Asia",
                      "genres": ["graphic design/poster"], "medium": "graphic_design",
                      "image": {"url": f"https://open-archive.test/media/work-{n:03d}.png", "width": 40, "height": 56},
                      "page": f"https://open-archive.test/works/OA-{n:03d}", "license": "CC0-1.0"})
    # 2010s: muted, light, low contrast editorial covers (synthetic)
    for i in range(12):
        n += 1
        light = [(236, 232, 224), (222, 226, 228), (240, 236, 230)][i % 3]
        img = png(56, 40, split(light, (210, 206, 200)))
        write(f"{h}/media/work-{n:03d}.png", img)
        items.append({"id": f"OA-{n:03d}", "title": f"Synthetic magazine cover {n}",
                      "creator": f"Fictional Studio {i % 4 + 1}", "date": f"201{i % 10}-0{i % 9 + 1}-15",
                      "year": None, "country": "KR" if i % 2 else "JP", "region": "East Asia",
                      "genres": ["editorial design/magazine cover"], "medium": "graphic_design",
                      "image": {"url": f"https://media.open-archive.test/work-{n:03d}.png", "width": 56, "height": 40},
                      "page": f"https://open-archive.test/works/OA-{n:03d}", "license": "CC0-1.0"})
        write(f"media.open-archive.test/work-{n:03d}.png", img)
    # Undated items: no year must ever be invented for these.
    for i in range(3):
        n += 1
        img = png(40, 40, solid((90 + i * 30, 90, 90)))
        write(f"{h}/media/work-{n:03d}.png", img)
        items.append({"id": f"OA-{n:03d}", "title": f"Undated photograph {n}", "creator": None, "date": None,
                      "year": "c. 1990s?", "country": None, "region": None, "genres": ["photography"],
                      "medium": "photograph",
                      "image": {"url": f"https://open-archive.test/media/work-{n:03d}.png"},
                      "page": None, "license": "CC0-1.0"})
    # An item whose image lives on a host the source does NOT allow.
    items.append({"id": "OA-900", "title": "Externally hosted image", "year": 2001, "genres": ["photography"],
                  "image": {"url": "https://cdn.unrelated.test/x.png"}, "license": "unknown"})
    # Same bytes as work-001 under another URL (dedup by hash).
    write(f"{h}/media/work-001-copy.png", (WEB / h / "media" / "work-001.png").read_bytes())
    items.append({"id": "OA-901", "title": "Duplicate scan of poster study 1", "year": 1980,
                  "country": "JP", "genres": ["graphic design/poster"], "medium": "graphic_design",
                  "image": {"url": "https://open-archive.test/media/work-001-copy.png"}, "license": "CC0-1.0"})
    write(f"{h}/api/catalog.json", json.dumps({"meta": {"note": "SYNTHETIC FIXTURE CATALOG"}, "items": items},
                                              indent=1, ensure_ascii=False))
    write(f"{h}/robots.txt", "User-agent: *\nAllow: /\n")
    write(f"media.open-archive.test/robots.txt", "User-agent: *\nAllow: /\n")
    write(f"{h}/terms.html", page("Open Archive terms (fixture)",
          "<p>SYNTHETIC FIXTURE. All images are CC0-1.0 test images.</p>"))


SOURCES = {
    "comment": "Offline fixture sources. Hosts use the reserved .test TLD; content is synthetic.",
    "sources": [
        {"id": "atelier", "name": "Atelier Journal (fixture)", "base_url": "https://atelier-journal.test/",
         "discovery_method": "sitemap", "policy_status": "allowed", "license": "CC0-1.0 (fixture)",
         "evidence_url": "https://atelier-journal.test/terms.html",
         "policy_note": "synthetic fixture content owned by this project"},
        {"id": "northlight", "name": "Northlight (fixture)", "base_url": "https://northlight-mag.test/",
         "discovery_method": "rss", "entry_urls": ["https://northlight-mag.test/feed.xml"]},
        {"id": "folio", "name": "Folio Review (fixture)", "base_url": "https://folio-review.test/",
         "discovery_method": "html", "policy_status": "review_required",
         "policy_note": "terms page not yet read"},
        {"id": "open-archive", "name": "Open Archive (fixture catalog)", "base_url": "https://open-archive.test/",
         "discovery_method": "json_catalog", "entry_urls": ["https://open-archive.test/api/catalog.json"],
         "allowed_asset_hosts": ["media.open-archive.test"],
         "catalog_mapping": {"items": "items", "image_url": "image.url", "page_url": "page", "title": "title",
                             "creator": "creator", "publication_date": "date", "year": "year",
                             "country": "country", "region": "region", "genres": "genres",
                             "media_type": "medium", "license": "license", "width": "image.width",
                             "height": "image.height"},
         "policy_status": "allowed", "license": "CC0-1.0", "evidence_url": "https://open-archive.test/terms.html"},
        {"id": "restricted-demo", "name": "Restricted demo (fixture)", "base_url": "https://atelier-journal.test/",
         "discovery_method": "sitemap", "policy_status": "restricted",
         "policy_note": "demonstrates refusal"},
        {"id": "disabled-demo", "name": "Disabled demo (fixture)", "base_url": "https://atelier-journal.test/",
         "discovery_method": "sitemap", "enabled": False},
    ],
}


def main() -> None:
    atelier()
    northlight()
    folio()
    archive()
    (ROOT / "sources.fixture.json").write_text(json.dumps(SOURCES, indent=2) + "\n", encoding="utf-8")
    print(f"fixtures written to {WEB}")


if __name__ == "__main__":
    main()
