"""Metadata extraction from one HTML document (no network access here).

Sources, in precedence order for each field: JSON-LD -> Open Graph / article:* ->
Twitter cards -> HTML <meta> -> HTML elements. The winning source of every
field is recorded in `field_sources`. Missing fields stay None. Problems
(broken JSON-LD, unparseable dates, ...) become warnings in `errors`; they
never abort extraction.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from .models import LANG_RE
from .timeutil import normalize_date
from .urls import try_normalize

ARTICLE_TYPES = {
    "article", "newsarticle", "blogposting", "report", "reportagenewsarticle",
    "analysisnewsarticle", "opinionnewsarticle", "reviewnewsarticle", "technarticle",
    "scholarlyarticle", "socialmediaposting", "liveblogposting", "backgroundnewsarticle",
}
TYPE_TO_PAGE = {
    **{t: "article" for t in ARTICLE_TYPES},
    "imagegallery": "gallery", "mediagallery": "gallery",
    "collectionpage": "collection", "itemlist": "collection",
    "videoobject": "video", "product": "product",
    "webpage": "web_page", "itempage": "web_page", "aboutpage": "web_page",
    "website": "homepage",
}
TYPE_PRIORITY = ["article", "gallery", "video", "product", "collection", "web_page", "homepage"]
OG_TYPE_TO_PAGE = {"article": "article", "video.other": "video", "video.movie": "video",
                   "product": "product", "website": "web_page"}
DATE_META_NAMES = ("date", "pubdate", "publish-date", "publish_date", "dc.date", "dc.date.issued",
                   "dcterms.created", "sailthru.date", "parsely-pub-date", "article.published")
SKIP_TEXT_TAGS = {"script", "style", "noscript", "template", "svg", "head", "title"}
MAX_IMAGES = 40


@dataclass
class ImageInfo:
    url: str
    role: str
    alt: str | None = None
    width: int | None = None
    height: int | None = None
    caption: str | None = None
    in_figure: bool = False
    position: int | None = None          # order among content images (0 = first)
    before_first_paragraph: bool = False


@dataclass
class PageExtract:
    url: str
    title: str | None = None
    description: str | None = None
    publisher: str | None = None
    canonical_url: str | None = None
    published_at: str | None = None
    modified_at: str | None = None
    language: str | None = None
    category: str | None = None
    authors: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    page_type: str = "unknown"
    access: str | None = None
    images: list[ImageInfo] = field(default_factory=list)
    field_sources: dict[str, str] = field(default_factory=dict)
    errors: list[dict] = field(default_factory=list)
    jsonld_types: list[str] = field(default_factory=list)
    robots_meta: set[str] = field(default_factory=set)
    links: list[tuple[str, str]] = field(default_factory=list)   # (absolute url, rel)
    theme_color: str | None = None
    declared_fonts: list[str] = field(default_factory=list)
    css_class_hints: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    text: str = ""
    raw_meta: dict = field(default_factory=dict)

    def warn(self, stage: str, code: str, message: str) -> None:
        self.errors.append({"stage": stage, "code": code, "message": message, "severity": "warning"})


def _int_attr(value: str | None) -> int | None:
    if value is None:
        return None
    m = re.match(r"^\s*(\d+)", str(value))
    if not m:
        return None
    n = int(m.group(1))
    return n if n > 0 else None


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text or None


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.anchors: list[tuple[str, str]] = []
        self.jsonld: list[str] = []
        self.styles: list[str] = []
        self.inline_styles: list[str] = []
        self.class_tokens: set[str] = set()
        self.title_parts: list[str] = []
        self.html_lang: str | None = None
        self.times: list[str] = []
        self.images: list[dict] = []
        self.counts = {f"h{i}": 0 for i in range(1, 7)}
        self.counts.update(p=0, figure=0, figcaption=0, blockquote=0, ul=0, ol=0, table=0,
                           article=0, aside=0, nav=0, img=0, picture=0)
        self.heading_texts: list[tuple[str, str]] = []
        self.text_parts: list[str] = []
        self.article_text_parts: list[str] = []
        self._stack: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._script_type: str | None = None
        self._script_buf: list[str] = []
        self._in_style = False
        self._style_buf: list[str] = []
        self._article_depth = 0
        self._figure_images: list[list[int]] = []
        self._in_figcaption = 0
        self._figcaption_buf: list[str] = []
        self._heading: str | None = None
        self._heading_buf: list[str] = []
        self._seen_paragraph = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if "class" in a:
            self.class_tokens.update(a["class"].lower().split())
        if a.get("style"):
            self.inline_styles.append(a["style"])
        if tag in ("meta",):
            self.meta.append(a)
            return
        if tag == "link":
            self.links.append(a)
            return
        if tag == "html" and a.get("lang"):
            self.html_lang = a["lang"]
        if tag == "img":
            self.counts["img"] += 1
            src = a.get("src") or a.get("data-src") or a.get("data-original")
            if not src and a.get("srcset"):
                src = _largest_srcset(a["srcset"])
            if src:
                self.images.append({"src": src, "alt": a.get("alt") if "alt" in a else None,
                                    "width": a.get("width"), "height": a.get("height"),
                                    "in_figure": bool(self._figure_images),
                                    "before_p": not self._seen_paragraph})
                if self._figure_images:
                    self._figure_images[-1].append(len(self.images) - 1)
            return
        if tag in ("br", "hr", "input", "source", "wbr", "area", "base", "col", "embed", "param",
                   "track"):
            return
        self._stack.append(tag)
        if tag in self.counts:
            self.counts[tag] += 1
        if tag in SKIP_TEXT_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        elif tag == "script":
            self._script_type = (a.get("type") or "").lower()
            self._script_buf = []
        elif tag == "style":
            self._in_style = True
            self._style_buf = []
        elif tag == "article":
            self._article_depth += 1
        elif tag == "figure":
            self._figure_images.append([])
        elif tag == "figcaption":
            self._in_figcaption += 1
            self._figcaption_buf = []
        elif tag == "p":
            self._seen_paragraph = True
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading = tag
            self._heading_buf = []
        elif tag == "time" and a.get("datetime"):
            self.times.append(a["datetime"])
        elif tag == "a" and a.get("href"):
            self.anchors.append((a["href"], a.get("rel", "").lower()))

    def handle_endtag(self, tag):
        if tag not in self._stack:
            return  # stray end tag in malformed HTML
        while self._stack:
            open_tag = self._stack.pop()
            self._close(open_tag)
            if open_tag == tag:
                break

    def _close(self, tag):
        if tag in SKIP_TEXT_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            if self._script_type == "application/ld+json":
                self.jsonld.append("".join(self._script_buf))
            self._script_type = None
        elif tag == "style":
            self._in_style = False
            self.styles.append("".join(self._style_buf))
        elif tag == "article":
            self._article_depth = max(0, self._article_depth - 1)
        elif tag == "figure":
            if self._figure_images:
                self._figure_images.pop()
        elif tag == "figcaption":
            self._in_figcaption = max(0, self._in_figcaption - 1)
            caption = _clean("".join(self._figcaption_buf))
            if caption and self._figure_images:
                for idx in self._figure_images[-1]:
                    self.images[idx].setdefault("caption", caption)
        elif tag == self._heading:
            text = _clean("".join(self._heading_buf))
            if text and len(self.heading_texts) < 30:
                self.heading_texts.append((tag, text))
            self._heading = None

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
            return
        if self._script_type is not None:
            self._script_buf.append(data)
            return
        if self._in_style:
            self._style_buf.append(data)
            return
        if self._skip_depth:
            return
        self.text_parts.append(data)
        if self._article_depth:
            self.article_text_parts.append(data)
        if self._in_figcaption:
            self._figcaption_buf.append(data)
        if self._heading:
            self._heading_buf.append(data)


def _largest_srcset(srcset: str) -> str | None:
    best, best_w = None, -1.0
    for part in srcset.split(","):
        bits = part.strip().split()
        if not bits:
            continue
        w = 0.0
        if len(bits) > 1:
            m = re.match(r"^(\d+(?:\.\d+)?)[wx]$", bits[1])
            w = float(m.group(1)) if m else 0.0
        if w > best_w:
            best, best_w = bits[0], w
    return best


# --------------------------------------------------------------------------- JSON-LD

def _parse_jsonld(raw: str, out: PageExtract) -> list:
    text = raw.strip()
    if not text:
        return []
    for attempt in range(2):
        try:
            return [json.loads(text)]
        except json.JSONDecodeError as exc:
            if attempt == 1:
                out.warn("jsonld", "jsonld_parse_error", f"invalid JSON-LD block: {exc.msg}")
                return []
            text = re.sub(r"^\s*(<!--|<!\[CDATA\[)|(-->|\]\]>)\s*$", "", text)
            text = re.sub(r",\s*([}\]])", r"\1", text)
            text = re.sub(r"[\x00-\x1f]", " ", text)
    return []


def _flatten(node, acc: list[dict]) -> None:
    if isinstance(node, list):
        for item in node:
            _flatten(item, acc)
    elif isinstance(node, dict):
        if "@graph" in node:
            _flatten(node["@graph"], acc)
        if "@type" in node:
            acc.append(node)


def _types(node: dict) -> list[str]:
    t = node.get("@type")
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [x for x in t if isinstance(x, str)]
    return []


def _page_kind(node: dict) -> str | None:
    kinds = [TYPE_TO_PAGE.get(t.lower()) for t in _types(node)]
    kinds = [k for k in kinds if k]
    for k in TYPE_PRIORITY:
        if k in kinds:
            return k
    return None


def _name(value) -> str | None:
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, dict):
        return _clean(value.get("name") if isinstance(value.get("name"), str) else None)
    if isinstance(value, list) and value:
        return _name(value[0])
    return None


def _names(value) -> list[str]:
    items = value if isinstance(value, list) else [value]
    out = []
    for item in items:
        n = _name(item)
        if n and n not in out:
            out.append(n)
    return out


def _jsonld_images(value) -> list[dict]:
    items = value if isinstance(value, list) else [value]
    out = []
    for item in items:
        if isinstance(item, str):
            out.append({"url": item})
        elif isinstance(item, dict):
            url = item.get("url") or item.get("contentUrl")
            if isinstance(url, str):
                out.append({"url": url, "width": _int_attr(item.get("width")),
                            "height": _int_attr(item.get("height")),
                            "caption": _clean(item.get("caption")) if isinstance(item.get("caption"), str) else None})
    return out


def _keywords(value) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"[,;|]", value)
    elif isinstance(value, list):
        parts = [p for p in value if isinstance(p, str)]
    else:
        return []
    out = []
    for p in parts:
        p = _clean(p)
        if p and p.lower() not in (x.lower() for x in out):
            out.append(p)
    return out


def _language(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip().replace("_", "-")
    parts = raw.split("-")
    tag = "-".join([parts[0].lower()] + [p.upper() if len(p) == 2 else p for p in parts[1:]])
    return tag if LANG_RE.match(tag) else None


def _google_font_families(href: str) -> list[str]:
    try:
        qs = parse_qs(urlsplit(href).query)
    except ValueError:
        return []
    out = []
    for fam in qs.get("family", []):
        for f in fam.split("|"):
            name = f.split(":")[0].replace("+", " ").strip()
            if name:
                out.append(name)
    return out


# --------------------------------------------------------------------------- main entry

def extract(html: str, url: str) -> PageExtract:
    out = PageExtract(url=url)
    col = _Collector()
    try:
        col.feed(html)
        col.close()
    except Exception as exc:  # noqa: BLE001 -- html.parser is lenient; keep what was collected
        out.warn("parse", "html_parse_error", f"{type(exc).__name__}: {exc}")

    meta: dict[str, str] = {}
    for m in col.meta:
        key = (m.get("property") or m.get("name") or m.get("itemprop") or m.get("http-equiv") or "").lower()
        if key and "content" in m and key not in meta:
            meta[key] = m["content"]
    out.raw_meta = meta
    links = {}
    for link in col.links:
        for rel in link.get("rel", "").lower().split():
            links.setdefault(rel, link.get("href"))
        if "fonts.googleapis.com" in link.get("href", ""):
            out.declared_fonts.extend(_google_font_families(link["href"]))

    # JSON-LD
    entities: list[dict] = []
    for block in col.jsonld:
        for doc in _parse_jsonld(block, out):
            _flatten(doc, entities)
    out.jsonld_types = sorted({t for e in entities for t in _types(e)})
    primary = None
    for kind in TYPE_PRIORITY:
        primary = next((e for e in entities if _page_kind(e) == kind), None)
        if primary:
            break
    site = next((e for e in entities if "WebSite" in _types(e)), None)
    org = next((e for e in entities if {"Organization", "NewsMediaOrganization"} & set(_types(e))), None)

    def setf(name: str, value, source: str) -> None:
        if value in (None, "", []):
            return
        if getattr(out, name) in (None, [], "unknown"):
            setattr(out, name, value)
            out.field_sources[name] = source

    if primary:
        setf("title", _clean(primary.get("headline") if isinstance(primary.get("headline"), str)
                             else primary.get("name") if isinstance(primary.get("name"), str) else None),
             "json-ld:headline")
        setf("description", _clean(primary.get("description")) if isinstance(primary.get("description"), str) else None,
             "json-ld:description")
        setf("publisher", _name(primary.get("publisher")), "json-ld:publisher")
        setf("authors", _names(primary.get("author")) if primary.get("author") else [], "json-ld:author")
        setf("category", _name(primary.get("articleSection")) if primary.get("articleSection") else None,
             "json-ld:articleSection")
        setf("keywords", _keywords(primary.get("keywords")), "json-ld:keywords")
        lang = primary.get("inLanguage")
        setf("language", _language(lang if isinstance(lang, str) else _name(lang)), "json-ld:inLanguage")
        for key, name in (("datePublished", "published_at"), ("dateModified", "modified_at")):
            raw = primary.get(key)
            if isinstance(raw, str):
                norm = normalize_date(raw)
                if norm is None:
                    out.warn("extract", "date_unparseable", f"{key} {raw!r} is not a date")
                setf(name, norm, f"json-ld:{key}")
        kind = _page_kind(primary)
        if kind:
            setf("page_type", kind, "json-ld:@type")
        free = primary.get("isAccessibleForFree")
        if free is not None:
            setf("access", "free" if str(free).lower() == "true" else "paywalled",
                 "json-ld:isAccessibleForFree")
    if site and not out.publisher:
        setf("publisher", _name(site.get("publisher")) or _name(site.get("name")), "json-ld:WebSite")
    if org and not out.publisher:
        setf("publisher", _name(org.get("name")), "json-ld:Organization")

    # Open Graph / article:* / Twitter / plain meta
    setf("title", _clean(meta.get("og:title")), "og:title")
    setf("title", _clean(meta.get("twitter:title")), "twitter:title")
    setf("description", _clean(meta.get("og:description")), "og:description")
    setf("description", _clean(meta.get("twitter:description")), "twitter:description")
    setf("description", _clean(meta.get("description")), "meta:description")
    setf("publisher", _clean(meta.get("og:site_name")), "og:site_name")
    setf("publisher", _clean(meta.get("publisher")), "meta:publisher")
    setf("category", _clean(meta.get("article:section")), "article:section")
    setf("category", _clean(meta.get("category") or meta.get("section")), "meta:category")
    setf("keywords", _keywords(meta.get("article:tag")), "article:tag")
    setf("keywords", _keywords(meta.get("keywords") or meta.get("news_keywords")), "meta:keywords")
    author = _clean(meta.get("author"))
    if author and not author.startswith("http"):
        setf("authors", [author], "meta:author")
    for key in ("article:published_time",) + DATE_META_NAMES:
        if key in meta and not out.published_at:
            norm = normalize_date(meta[key])
            if norm is None:
                out.warn("extract", "date_unparseable", f"{key} {meta[key]!r} is not a date")
            setf("published_at", norm, f"meta:{key}")
    if "article:modified_time" in meta:
        setf("modified_at", normalize_date(meta["article:modified_time"]), "article:modified_time")
    if not out.published_at and col.times:
        setf("published_at", normalize_date(col.times[0]), "html:time")
    setf("language", _language(meta.get("og:locale")), "og:locale")
    setf("language", _language(col.html_lang), "html:lang")
    setf("language", _language(meta.get("content-language")), "meta:content-language")
    og_type = (meta.get("og:type") or "").lower()
    if og_type in OG_TYPE_TO_PAGE:
        setf("page_type", OG_TYPE_TO_PAGE[og_type], "og:type")
    setf("title", _clean("".join(col.title_parts)), "html:title")
    if out.page_type == "unknown" and urlsplit(url).path in ("", "/"):
        out.page_type = "homepage"
        out.field_sources["page_type"] = "rule:root-path"

    canonical = try_normalize(links.get("canonical"), base=url) if links.get("canonical") else None
    if links.get("canonical") and canonical is None:
        out.warn("extract", "canonical_invalid", f"invalid canonical link {links.get('canonical')!r}")
    if canonical:
        out.canonical_url = canonical
        out.field_sources["canonical_url"] = "link:canonical"
    elif meta.get("og:url") and try_normalize(meta["og:url"], base=url):
        out.canonical_url = try_normalize(meta["og:url"], base=url)
        out.field_sources["canonical_url"] = "og:url"

    robots = (meta.get("robots") or "") + "," + (meta.get("googlebot") or "")
    out.robots_meta = {t.strip().lower() for t in robots.split(",") if t.strip()}
    out.theme_color = _clean(meta.get("theme-color"))

    # Images: metadata images first, then content images.
    seen: dict[str, ImageInfo] = {}

    def add_image(raw_url, role, alt=None, width=None, height=None, caption=None, **kw) -> None:
        norm = try_normalize(raw_url, base=url) if raw_url and not str(raw_url).startswith("data:") else None
        if norm is None or len(seen) >= MAX_IMAGES:
            return
        if urlsplit(norm).path.lower().endswith(".svg"):
            return
        if width is not None and height is not None and width <= 2 and height <= 2:
            return  # tracking pixel
        if norm in seen:
            img = seen[norm]
            img.alt = img.alt or alt
            img.caption = img.caption or caption
            img.width = img.width or width
            img.height = img.height or height
            for k, v in kw.items():
                if getattr(img, k) in (None, False):
                    setattr(img, k, v)
            return
        seen[norm] = ImageInfo(norm, role, _clean(alt) if alt else alt, width, height,
                               _clean(caption), **kw)

    og_img = meta.get("og:image") or meta.get("og:image:url") or meta.get("og:image:secure_url")
    if og_img:
        add_image(og_img, "og_image", meta.get("og:image:alt"),
                  _int_attr(meta.get("og:image:width")), _int_attr(meta.get("og:image:height")))
    if meta.get("twitter:image"):
        add_image(meta["twitter:image"], "twitter_image", meta.get("twitter:image:alt"))
    if primary and primary.get("image"):
        for im in _jsonld_images(primary.get("image")):
            add_image(im["url"], "jsonld_image", None, im.get("width"), im.get("height"), im.get("caption"))
    for pos, im in enumerate(col.images):
        add_image(im["src"], "inline", im.get("alt"), _int_attr(im.get("width")),
                  _int_attr(im.get("height")), im.get("caption"), in_figure=im["in_figure"],
                  position=pos, before_first_paragraph=im["before_p"])
    out.images = list(seen.values())
    if out.images:
        primary_url = out.images[0].url if out.images[0].role != "inline" else None
        if primary_url is None:
            primary_url = out.images[0].url
        for img in out.images:
            if img.url == primary_url:
                img.role = "primary"
                break

    # Links for HTML discovery (absolute, normalized, nofollow-aware).
    for href, rel in col.anchors:
        norm = try_normalize(href, base=url)
        if norm:
            out.links.append((norm, rel))

    # Typography as declared in CSS source (not rendered).
    css = "\n".join(col.styles + col.inline_styles)
    for fam in re.findall(r"font-family\s*:\s*([^;}{]+)", css, flags=re.I):
        for name in fam.split(","):
            name = name.strip().strip("'\"")
            if name and name.lower() not in (f.lower() for f in out.declared_fonts) and len(name) < 60:
                out.declared_fonts.append(name)
    hints = sorted(t for t in col.class_tokens
                   if re.search(r"(grid|col-|column|layout|hero|asym|offset|span-)", t))[:20]
    out.css_class_hints = hints

    body_text = _clean(" ".join(col.article_text_parts)) or _clean(" ".join(col.text_parts)) or ""
    out.text = body_text[:200_000]
    words = len(re.findall(r"\w+", body_text))
    content_images = [i for i in out.images if i.position is not None]
    out.stats = {
        "word_count": words,
        "paragraphs": col.counts["p"],
        "headings": {k: col.counts[k] for k in ("h1", "h2", "h3", "h4", "h5", "h6")},
        "heading_texts": col.heading_texts[:10],
        "figures": col.counts["figure"],
        "figcaptions": col.counts["figcaption"],
        "blockquotes": col.counts["blockquote"],
        "lists": col.counts["ul"] + col.counts["ol"],
        "tables": col.counts["table"],
        "content_images": len(content_images),
        "article_element": col.counts["article"] > 0,
        "image_before_first_paragraph": any(i.before_first_paragraph for i in content_images),
        "text_scope": "article" if col.article_text_parts else "body",
    }
    return out
