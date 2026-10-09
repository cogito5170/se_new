"""Data contract `magazine_image_reference/1` (one record per image URL / asset).

Field rules:
  id                      'mi_' + 20 hex chars (SHA-256 of the normalized original URL)
  image.type              cover|interior_page|editorial_photo|portrait|product_photo|other
  image.type_evidence     {status: observed|inferred|unverified, method, basis}
  image.original_url      required http(s) URL as discovered (normalized)
  image.final_url         URL after redirects of the successful download, else null
  image.local_path        absolute path of the stored file, else null
  image.relative_path     path below the data root, else null
  image.mime_type/width/height/size_bytes/sha256   from the stored bytes, else null
  image.file_status       ok|missing|corrupt|relocated|null
  work.*                  descriptive metadata; unknown -> null. year_start/end are the
                          work's years and only come from explicit data (see year_basis)
  rights.policy_status    unknown|review_required|allowed|restricted (effective policy)
  rights.policy_scope     'image' (image-level review) or 'source' (inherited)
  download.status         pending|downloaded|failed_transient|failed_permanent|blocked|missing_file
  features.measured[] / features.semantic[]   rows of visual_features
"""
from __future__ import annotations

import re

from .assets import DOWNLOAD_STATUSES, MEDIA_TYPES
from .features import IMAGE_TYPES
from .models import POLICY_STATUSES, URL_RE, _V
from .timeutil import is_iso8601, is_utc_timestamp

IMAGE_SCHEMA_VERSION = "magazine_image_reference/1"
IMAGE_ID_RE = re.compile(r"^mi_[0-9a-f]{20}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
FILE_STATUSES = ("ok", "missing", "corrupt", "relocated")


def _url(v: str) -> bool:
    return bool(URL_RE.match(v))


def validate_image_record(rec) -> list[str]:
    v = _V()
    if not v.obj(rec, "$", ("schema", "id", "image", "work", "source", "rights", "download",
                            "features", "duplicates", "timestamps")):
        return v.errors
    if rec.get("schema") != IMAGE_SCHEMA_VERSION:
        v.err("$.schema", f"must be '{IMAGE_SCHEMA_VERSION}'")
    v.field(rec, "id", "$", (str,), False, check=lambda s: bool(IMAGE_ID_RE.match(s)),
            check_msg="must match mi_<20 hex>")
    img = rec.get("image")
    if v.obj(img, "$.image", ("type", "type_evidence", "original_url", "final_url", "local_path",
                              "relative_path", "mime_type", "width", "height", "size_bytes",
                              "sha256", "file_status", "media_type")):
        p = "$.image"
        v.field(img, "type", p, (str,), False, enum=IMAGE_TYPES)
        te = img.get("type_evidence")
        if v.obj(te, p + ".type_evidence", ("status", "method", "basis")):
            v.field(te, "status", p + ".type_evidence", (str,), False,
                    enum=("observed", "inferred", "unverified"))
            v.field(te, "method", p + ".type_evidence", (str,), True)
            v.field(te, "basis", p + ".type_evidence", (str,), True)
        v.field(img, "original_url", p, (str,), False, check=_url, check_msg="must be http(s) URL")
        v.field(img, "final_url", p, (str,), True, check=_url, check_msg="must be http(s) URL")
        v.field(img, "local_path", p, (str,), True)
        v.field(img, "relative_path", p, (str,), True,
                check=lambda s: not s.startswith("/") and ".." not in s.split("/"),
                check_msg="must be a relative path without '..'")
        v.field(img, "mime_type", p, (str,), True, enum=("image/png", "image/jpeg", "image/gif", "image/webp"))
        for k in ("width", "height", "size_bytes"):
            v.field(img, k, p, (int,), True, check=lambda n: n > 0, check_msg="must be > 0")
        v.field(img, "sha256", p, (str,), True, check=lambda s: bool(SHA_RE.match(s)),
                check_msg="must be 64 lowercase hex")
        v.field(img, "file_status", p, (str,), True, enum=FILE_STATUSES)
        v.field(img, "media_type", p, (str,), False, enum=MEDIA_TYPES)
        stored = img.get("sha256") is not None
        for k in ("local_path", "relative_path", "mime_type", "size_bytes"):
            if stored and img.get(k) is None:
                v.err(p, f"{k} is required when sha256 is set")
    work = rec.get("work")
    if v.obj(work, "$.work", ("title", "creator", "description", "alt", "caption", "publication_date",
                              "creation_date", "upload_date", "year_start", "year_end", "year_basis",
                              "country", "region", "genres")):
        p = "$.work"
        for k in ("title", "creator", "description", "alt", "caption", "country", "region"):
            v.field(work, k, p, (str,), True)
        for k in ("publication_date", "creation_date", "upload_date"):
            v.field(work, k, p, (str,), True, check=is_iso8601, check_msg="must be ISO 8601")
        for k in ("year_start", "year_end"):
            v.field(work, k, p, (int,), True, check=lambda n: 1000 <= n <= 2999, check_msg="implausible year")
        v.field(work, "year_basis", p, (str,), True,
                enum=("publication", "creation", "circa", "source_declared"))
        ys, ye = work.get("year_start"), work.get("year_end")
        if (ys is None) != (ye is None):
            v.err(p, "year_start and year_end must both be set or both be null")
        if isinstance(ys, int) and isinstance(ye, int) and ys > ye:
            v.err(p, "year_start must be <= year_end")
        if ys is not None and work.get("year_basis") is None:
            v.err(p, "year_basis is required when years are set")
        v.str_list(work, "genres", p)
    src = rec.get("source")
    if v.obj(src, "$.source", ("source_id", "publisher", "source_page_url", "page_reference_id",
                               "discovery_method")):
        v.field(src, "source_id", "$.source", (str,), False)
        v.field(src, "publisher", "$.source", (str,), True)
        v.field(src, "source_page_url", "$.source", (str,), True, check=_url, check_msg="must be http(s) URL")
        v.field(src, "page_reference_id", "$.source", (str,), True)
        v.field(src, "discovery_method", "$.source", (str,), False,
                enum=("sitemap", "rss", "html", "json_catalog", "import"))
    rights = rec.get("rights")
    if v.obj(rights, "$.rights", ("policy_status", "policy_scope", "license", "declared_license",
                                  "evidence_url", "reviewed_at", "note")):
        v.field(rights, "policy_status", "$.rights", (str,), False, enum=POLICY_STATUSES)
        v.field(rights, "policy_scope", "$.rights", (str,), False, enum=("image", "source"))
        for k in ("license", "declared_license", "note"):
            v.field(rights, k, "$.rights", (str,), True)
        v.field(rights, "evidence_url", "$.rights", (str,), True, check=_url, check_msg="must be http(s) URL")
        v.field(rights, "reviewed_at", "$.rights", (str,), True, check=is_utc_timestamp,
                check_msg="must be UTC timestamp")
        if rights.get("policy_status") == "allowed" and not (rights.get("license") or rights.get("evidence_url")):
            v.err("$.rights", "'allowed' requires license or evidence_url")
    dl = rec.get("download")
    if v.obj(dl, "$.download", ("status", "attempt_count", "last_attempt_at", "last_error",
                                "last_error_class")):
        v.field(dl, "status", "$.download", (str,), False, enum=DOWNLOAD_STATUSES)
        v.field(dl, "attempt_count", "$.download", (int,), False, check=lambda n: n >= 0,
                check_msg="must be >= 0")
        v.field(dl, "last_attempt_at", "$.download", (str,), True, check=is_utc_timestamp,
                check_msg="must be UTC timestamp")
        v.field(dl, "last_error", "$.download", (str,), True)
        v.field(dl, "last_error_class", "$.download", (str,), True, enum=("transient", "permanent"))
        if dl.get("status") == "downloaded" and isinstance(img, dict) and img.get("sha256") is None:
            v.err("$.download", "downloaded records must carry image.sha256")
    feats = rec.get("features")
    if v.obj(feats, "$.features", ("measured", "semantic")):
        for kind in ("measured", "semantic"):
            items = feats.get(kind)
            if not isinstance(items, list):
                v.err(f"$.features.{kind}", "must be an array")
                continue
            for i, f in enumerate(items):
                p = f"$.features.{kind}[{i}]"
                if v.obj(f, p, ("feature_type", "feature_value", "method", "tool", "confidence",
                                "review_status", "evidence_note")):
                    v.field(f, "feature_type", p, (str,), False)
                    v.field(f, "feature_value", p, (str,), False)
                    v.field(f, "method", p, (str,), False)
                    v.field(f, "tool", p, (str,), True)
                    v.field(f, "confidence", p, (int, float), True)
                    v.field(f, "review_status", p, (str,), False,
                            enum=("auto_measured", "ai_suggested", "human_entered", "human_reviewed"))
                    if kind == "measured" and f.get("review_status") != "auto_measured":
                        v.err(p, "measured features must be auto_measured")
                    if f.get("review_status") == "ai_suggested" and not f.get("tool"):
                        v.err(p, "AI suggestions must name the tool/model")
    dup = rec.get("duplicates")
    if v.obj(dup, "$.duplicates", ("same_file_as",)):
        v.str_list(dup, "same_file_as", "$.duplicates")
    ts = rec.get("timestamps")
    if v.obj(ts, "$.timestamps", ("discovered_at", "updated_at")):
        for k in ("discovered_at", "updated_at"):
            v.field(ts, k, "$.timestamps", (str,), False, check=is_utc_timestamp,
                    check_msg="must be UTC timestamp")
    return v.errors
