"""Data contract `magazine_reference/1`: enums, field rules and validation.

The validator in this module is the authority. `json_schema()` emits an
equivalent JSON Schema (draft 2020-12) for external consumers such as a
future orchestrator or InDesign UXP plugin; `schema/magazine_reference-1.schema.json`
is generated from it (`magref schema`) and a test keeps the two in sync.
"""
from __future__ import annotations

import re
from typing import Any

from .timeutil import is_iso8601, is_utc_timestamp

SCHEMA_VERSION = "magazine_reference/1"
EXPORT_SCHEMA_VERSION = "magazine_reference_export/1"   # envelope; see magref.export
EXTRACTOR_VERSION = "magref-extract/1"

DISCOVERY_METHODS = ("sitemap", "rss", "html", "json_catalog")
# How the reference entered this repository (adds 'import' for records loaded from a file).
REFERENCE_ORIGINS = DISCOVERY_METHODS + ("import",)
# Access-policy status (of a source, or of one image via an image-level review).
# Assigned by a human review that records its evidence; robots.txt alone never
# makes anything 'allowed', and reachability of a public URL is not permission.
#   allowed          evidence that this collection/download method is permitted
#   restricted       terms, licence or access restrictions forbid download
#   unknown          not (yet) checked -- the default
#   review_required  someone looked and more review is needed
POLICY_STATUSES = ("unknown", "review_required", "allowed", "restricted")
DOWNLOADABLE_POLICY = "allowed"
# Result of the robots.txt check for one URL.
ROBOTS_STATUSES = ("allowed", "disallowed", "unavailable", "not_checked")
PAGE_TYPES = (
    "web_page", "article", "gallery", "collection", "homepage", "video", "product", "unknown",
)
CRAWL_STATUSES = ("pending", "fetched", "failed", "skipped", "blocked")
ANALYSIS_STATUSES = ("pending", "partial", "complete", "failed")
EVIDENCE_STATUSES = ("observed", "inferred", "unverified")
ASSET_ROLES = ("primary", "inline", "og_image", "twitter_image", "jsonld_image")
DIMENSION_SOURCES = ("image_header", "image_decoded", "html_attribute", "metadata")
ERROR_STAGES = ("robots", "fetch", "parse", "jsonld", "extract", "image", "validation", "policy")
SEVERITIES = ("error", "warning")

DESIGN_FEATURES = (
    "page_type",
    "visual_hierarchy",
    "grid_structure",
    "typography",
    "whitespace",
    "image_composition",
    "aspect_ratio",
    "dominant_colors",
    "text_density",
    "editorial_structure",
)

ID_RE = re.compile(r"^mr_[0-9a-f]{20}$")
URL_RE = re.compile(r"^https?://[^\s/]+/\S*$")
SOURCE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


class ValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors[:5]) + (" ..." if len(errors) > 5 else ""))
        self.errors = errors


# --------------------------------------------------------------------------- helpers

def _type_ok(value: Any, kinds: tuple, nullable: bool) -> bool:
    if value is None:
        return nullable
    if bool in kinds:
        return isinstance(value, bool)
    if isinstance(value, bool):  # bool is an int subclass; never accept it as a number
        return False
    return isinstance(value, kinds)


class _V:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def err(self, path: str, msg: str) -> None:
        self.errors.append(f"{path}: {msg}")

    def obj(self, value: Any, path: str, required: tuple, optional: tuple = ()) -> bool:
        if not isinstance(value, dict):
            self.err(path, "must be an object")
            return False
        for key in required:
            if key not in value:
                self.err(path, f"missing required field '{key}'")
        allowed = set(required) | set(optional)
        for key in value:
            if key not in allowed:
                self.err(path, f"unexpected field '{key}'")
        return True

    def field(self, d: dict, key: str, path: str, kinds: tuple, nullable: bool,
              enum: tuple | None = None, check=None, check_msg: str = "") -> None:
        if key not in d:
            return
        value = d[key]
        if not _type_ok(value, kinds, nullable):
            names = "/".join(k.__name__ for k in kinds) + (" or null" if nullable else "")
            self.err(f"{path}.{key}", f"must be {names}, got {type(value).__name__}")
            return
        if value is None:
            return
        if enum is not None and value not in enum:
            self.err(f"{path}.{key}", f"must be one of {list(enum)}, got {value!r}")
        if check is not None and not check(value):
            self.err(f"{path}.{key}", check_msg or "invalid value")

    def str_list(self, d: dict, key: str, path: str) -> None:
        if key not in d:
            return
        value = d[key]
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            self.err(f"{path}.{key}", "must be an array of strings")


def _is_url(v: str) -> bool:
    return bool(URL_RE.match(v))


# --------------------------------------------------------------------------- validator

def validate_reference(ref: Any) -> list[str]:
    """Return a list of human-readable problems; empty list means valid."""
    v = _V()
    top_required = ("schema", "id", "source", "content", "assets", "visual_features",
                    "analysis", "processing", "provenance")
    if not v.obj(ref, "$", top_required):
        return v.errors
    if ref.get("schema") != SCHEMA_VERSION:
        v.err("$.schema", f"must be '{SCHEMA_VERSION}'")
    v.field(ref, "id", "$", (str,), False, check=lambda s: bool(ID_RE.match(s)),
            check_msg="must match mr_<20 hex>")

    src = ref.get("source")
    if v.obj(src, "$.source", ("source_id", "name", "publisher", "url", "canonical_url",
                               "discovery_method", "discovered_from", "policy_status", "robots")):
        v.field(src, "source_id", "$.source", (str,), False,
                check=lambda s: bool(SOURCE_ID_RE.match(s)), check_msg="invalid source id")
        v.field(src, "name", "$.source", (str,), True)
        v.field(src, "publisher", "$.source", (str,), True)
        v.field(src, "url", "$.source", (str,), False, check=_is_url, check_msg="must be http(s) URL")
        v.field(src, "canonical_url", "$.source", (str,), True, check=_is_url,
                check_msg="must be http(s) URL")
        v.field(src, "discovery_method", "$.source", (str,), False, enum=REFERENCE_ORIGINS)
        v.field(src, "discovered_from", "$.source", (str,), True)
        v.field(src, "policy_status", "$.source", (str,), False, enum=POLICY_STATUSES)
        v.field(src, "robots", "$.source", (str,), False, enum=ROBOTS_STATUSES)

    content = ref.get("content")
    if v.obj(content, "$.content", ("title", "description", "category", "published_at",
                                    "modified_at", "language", "page_type", "authors",
                                    "keywords", "access")):
        for key in ("title", "description", "category"):
            v.field(content, key, "$.content", (str,), True)
        for key in ("published_at", "modified_at"):
            v.field(content, key, "$.content", (str,), True, check=is_iso8601,
                    check_msg="must be ISO 8601")
        v.field(content, "language", "$.content", (str,), True,
                check=lambda s: bool(LANG_RE.match(s)), check_msg="must be a BCP 47 tag")
        v.field(content, "page_type", "$.content", (str,), False, enum=PAGE_TYPES)
        v.str_list(content, "authors", "$.content")
        v.str_list(content, "keywords", "$.content")
        v.field(content, "access", "$.content", (str,), True,
                enum=("free", "paywalled", "unknown"))

    assets = ref.get("assets")
    if not isinstance(assets, list):
        v.err("$.assets", "must be an array")
    else:
        for i, asset in enumerate(assets):
            p = f"$.assets[{i}]"
            if not v.obj(asset, p, ("url", "role", "alt", "width", "height",
                                    "dimension_source", "downloaded")):
                continue
            v.field(asset, "url", p, (str,), False, check=_is_url, check_msg="must be http(s) URL")
            v.field(asset, "role", p, (str,), False, enum=ASSET_ROLES)
            v.field(asset, "alt", p, (str,), True)
            v.field(asset, "width", p, (int,), True, check=lambda n: n > 0, check_msg="must be > 0")
            v.field(asset, "height", p, (int,), True, check=lambda n: n > 0, check_msg="must be > 0")
            v.field(asset, "dimension_source", p, (str,), True, enum=DIMENSION_SOURCES)
            v.field(asset, "downloaded", p, (str,), False, enum=("none", "partial", "full"))
            if (asset.get("width") is None) != (asset.get("height") is None):
                v.err(p, "width and height must both be set or both be null")
            if asset.get("width") is not None and asset.get("dimension_source") is None:
                v.err(p, "dimension_source is required when dimensions are set")

    vf = ref.get("visual_features")
    if v.obj(vf, "$.visual_features", DESIGN_FEATURES):
        for name in DESIGN_FEATURES:
            if name not in vf:
                continue
            p = f"$.visual_features.{name}"
            feat = vf[name]
            if not v.obj(feat, p, ("status", "value", "method", "basis")):
                continue
            v.field(feat, "status", p, (str,), False, enum=EVIDENCE_STATUSES)
            v.field(feat, "method", p, (str,), True)
            v.field(feat, "basis", p, (str,), True)
            if feat.get("status") == "unverified" and feat.get("value") is not None:
                v.err(p, "an unverified feature must have value null")
            if feat.get("status") in ("observed", "inferred") and not feat.get("method"):
                v.err(p, "observed/inferred features must name their method")

    analysis = ref.get("analysis")
    if v.obj(analysis, "$.analysis", EVIDENCE_STATUSES):
        for status in EVIDENCE_STATUSES:
            items = analysis.get(status)
            if not isinstance(items, list):
                v.err(f"$.analysis.{status}", "must be an array")
                continue
            for i, item in enumerate(items):
                p = f"$.analysis.{status}[{i}]"
                if v.obj(item, p, ("feature", "claim", "method")):
                    v.field(item, "feature", p, (str,), False, enum=DESIGN_FEATURES)
                    v.field(item, "claim", p, (str,), False)
                    v.field(item, "method", p, (str,), True)

    proc = ref.get("processing")
    if v.obj(proc, "$.processing", ("crawl_status", "analysis_status", "http_status", "errors",
                                    "first_seen_at", "last_crawled_at", "extractor_version")):
        v.field(proc, "crawl_status", "$.processing", (str,), False, enum=CRAWL_STATUSES)
        v.field(proc, "analysis_status", "$.processing", (str,), False, enum=ANALYSIS_STATUSES)
        v.field(proc, "http_status", "$.processing", (int,), True,
                check=lambda n: 100 <= n <= 599, check_msg="must be an HTTP status")
        v.field(proc, "first_seen_at", "$.processing", (str,), False, check=is_utc_timestamp,
                check_msg="must be UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
        v.field(proc, "last_crawled_at", "$.processing", (str,), True, check=is_utc_timestamp,
                check_msg="must be UTC timestamp YYYY-MM-DDTHH:MM:SSZ")
        v.field(proc, "extractor_version", "$.processing", (str,), True)
        errors = proc.get("errors")
        if not isinstance(errors, list):
            v.err("$.processing.errors", "must be an array")
        else:
            for i, e in enumerate(errors):
                p = f"$.processing.errors[{i}]"
                if v.obj(e, p, ("stage", "code", "message", "severity", "at")):
                    v.field(e, "stage", p, (str,), False, enum=ERROR_STAGES)
                    v.field(e, "code", p, (str,), False)
                    v.field(e, "message", p, (str,), False)
                    v.field(e, "severity", p, (str,), False, enum=SEVERITIES)
                    v.field(e, "at", p, (str,), False, check=is_utc_timestamp,
                            check_msg="must be UTC timestamp")
        if proc.get("crawl_status") == "fetched" and proc.get("last_crawled_at") is None:
            v.err("$.processing", "fetched references must have last_crawled_at")

    prov = ref.get("provenance")
    if v.obj(prov, "$.provenance", ("fetched_url", "fetched_at", "field_sources", "aliases")):
        v.field(prov, "fetched_url", "$.provenance", (str,), True, check=_is_url,
                check_msg="must be http(s) URL")
        v.field(prov, "fetched_at", "$.provenance", (str,), True, check=is_utc_timestamp,
                check_msg="must be UTC timestamp")
        fs = prov.get("field_sources")
        if not isinstance(fs, dict) or not all(isinstance(x, str) for x in fs.values()):
            v.err("$.provenance.field_sources", "must be an object of strings")
        v.str_list(prov, "aliases", "$.provenance")
    return v.errors


# --------------------------------------------------------------------------- JSON Schema

def _nullable(schema: dict) -> dict:
    t = schema.get("type")
    out = dict(schema)
    if isinstance(t, str):
        out["type"] = [t, "null"]
    if "enum" in out:
        out["enum"] = list(out["enum"]) + [None]
    return out


def json_schema() -> dict:
    s_str = {"type": "string"}
    url = {"type": "string", "pattern": URL_RE.pattern}
    ts = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"}
    iso = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}"}
    str_arr = {"type": "array", "items": s_str}

    def closed(props: dict) -> dict:
        return {"type": "object", "properties": props, "required": list(props),
                "additionalProperties": False}

    feature = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": list(EVIDENCE_STATUSES)},
            "value": {},
            "method": _nullable(s_str),
            "basis": _nullable(s_str),
        },
        "required": ["status", "value", "method", "basis"],
        "additionalProperties": False,
        "if": {"properties": {"status": {"const": "unverified"}}},
        "then": {"properties": {"value": {"type": "null"}}},
    }
    claim = closed({
        "feature": {"type": "string", "enum": list(DESIGN_FEATURES)},
        "claim": s_str,
        "method": _nullable(s_str),
    })
    error = closed({
        "stage": {"type": "string", "enum": list(ERROR_STAGES)},
        "code": s_str,
        "message": s_str,
        "severity": {"type": "string", "enum": list(SEVERITIES)},
        "at": ts,
    })
    asset = closed({
        "url": url,
        "role": {"type": "string", "enum": list(ASSET_ROLES)},
        "alt": _nullable(s_str),
        "width": {"type": ["integer", "null"], "minimum": 1},
        "height": {"type": ["integer", "null"], "minimum": 1},
        "dimension_source": _nullable({"type": "string", "enum": list(DIMENSION_SOURCES)}),
        "downloaded": {"type": "string", "enum": ["none", "partial", "full"]},
    })
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "magazine_reference-1.schema.json",
        "title": SCHEMA_VERSION,
        "description": "One source-backed magazine/editorial design reference. Generated by "
                       "`magref schema`; the Python validator in magref.models is authoritative.",
        **closed({
            "schema": {"const": SCHEMA_VERSION},
            "id": {"type": "string", "pattern": ID_RE.pattern},
            "source": closed({
                "source_id": {"type": "string", "pattern": SOURCE_ID_RE.pattern},
                "name": _nullable(s_str),
                "publisher": _nullable(s_str),
                "url": url,
                "canonical_url": _nullable(url),
                "discovery_method": {"type": "string", "enum": list(REFERENCE_ORIGINS)},
                "discovered_from": _nullable(s_str),
                "policy_status": {"type": "string", "enum": list(POLICY_STATUSES)},
                "robots": {"type": "string", "enum": list(ROBOTS_STATUSES)},
            }),
            "content": closed({
                "title": _nullable(s_str),
                "description": _nullable(s_str),
                "category": _nullable(s_str),
                "published_at": _nullable(iso),
                "modified_at": _nullable(iso),
                "language": _nullable({"type": "string", "pattern": LANG_RE.pattern}),
                "page_type": {"type": "string", "enum": list(PAGE_TYPES)},
                "authors": str_arr,
                "keywords": str_arr,
                "access": _nullable({"type": "string", "enum": ["free", "paywalled", "unknown"]}),
            }),
            "assets": {"type": "array", "items": asset},
            "visual_features": closed({name: feature for name in DESIGN_FEATURES}),
            "analysis": closed({s: {"type": "array", "items": claim} for s in EVIDENCE_STATUSES}),
            "processing": closed({
                "crawl_status": {"type": "string", "enum": list(CRAWL_STATUSES)},
                "analysis_status": {"type": "string", "enum": list(ANALYSIS_STATUSES)},
                "http_status": {"type": ["integer", "null"], "minimum": 100, "maximum": 599},
                "errors": {"type": "array", "items": error},
                "first_seen_at": ts,
                "last_crawled_at": _nullable(ts),
                "extractor_version": _nullable(s_str),
            }),
            "provenance": closed({
                "fetched_url": _nullable(url),
                "fetched_at": _nullable(ts),
                "field_sources": {"type": "object", "additionalProperties": s_str},
                "aliases": str_arr,
            }),
        }),
    }
