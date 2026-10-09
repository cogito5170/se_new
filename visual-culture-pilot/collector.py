#!/usr/bin/env python3
"""Bounded pilot collector for The Met Collection API.

Searches a small fixed set of terms, inspects object records one at a time,
keeps only records whose API ``isPublicDomain`` flag is true and whose
``primaryImage`` is an official Met image URL, downloads at most 10 images,
validates each file, and appends one JSON line per saved image to
``manifests/collection_manifest.jsonl``.

Standard library only, plus Pillow for image validation.

    python3 collector.py                      # live run: seed object 436121 first, then search
    python3 collector.py --replay RUN_ID      # re-plan from saved API snapshots (no downloads)
    python3 collector.py --plan-only          # stop after selection; no downloads

Python 3.9+.
"""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import json
import logging
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:  # reported by the environment check; the collector refuses to run
    Image = None
    UnidentifiedImageError = Exception

PROJECT_DIR = Path(__file__).resolve().parent
ARCHIVE_DIR = PROJECT_DIR / "visual_culture_archive"

API_ROOT = "https://collectionapi.metmuseum.org"
SEARCH_URL = API_ROOT + "/public/collection/v1/search"
OBJECT_URL = API_ROOT + "/public/collection/v1/objects/{object_id}"
DOCS_URL = "https://metmuseum.github.io/"
RIGHTS_POLICY_URL = "https://www.metmuseum.org/about-the-met/policies-and-documents/open-access"
SOURCE_INSTITUTION = "The Metropolitan Museum of Art"
LICENSE_ID = "CC0-1.0"
OFFICIAL_IMAGE_HOSTS = frozenset({"images.metmuseum.org"})
OFFICIAL_API_HOSTS = frozenset({"collectionapi.metmuseum.org"})
ALLOWED_HOSTS = OFFICIAL_IMAGE_HOSTS | OFFICIAL_API_HOSTS

DEFAULT_TERMS = ("poster", "print", "typography", "textile", "photograph")
DEFAULT_SEED_OBJECTS = (436121,)
HARD_MAX_IMAGES = 10
MIN_REQUEST_INTERVAL = 0.5
USER_AGENT = "visual-culture-archive-pilot/0.1 (bounded validation pilot; concurrency 1)"

MAX_JSON_BYTES = 5 * 1024 * 1024
MAX_IMAGE_BYTES = 40 * 1024 * 1024
IMAGE_FORMAT_EXT = {"JPEG": ".jpg", "PNG": ".png", "GIF": ".gif", "TIFF": ".tif", "WEBP": ".webp"}

REQUIRED_FIELDS = (
    "record_id", "title", "creator", "creation_year", "publication_year",
    "country_or_region", "genre", "medium", "source_institution", "source_record_url",
    "original_image_url", "local_file_path", "is_public_domain", "license",
    "license_evidence_url", "attribution_text", "collected_at", "sha256",
    "file_size_bytes", "image_validation_status", "metadata_confidence", "context_claims",
)
# Fields whose value is copied from the source record (may legitimately be null).
SOURCE_DESCRIPTIVE_FIELDS = (
    "title", "creator", "creation_year", "publication_year", "country_or_region", "genre", "medium",
)

REMEDIATION = {
    "network_blocked": "The egress proxy refused the host. Allow collectionapi.metmuseum.org and "
                       "images.metmuseum.org in the environment's network policy, then re-run.",
    "network_error": "Transient connection failure. Re-run later; the collector skips records already in the manifest.",
    "timeout": "Request exceeded the timeout. Re-run later or raise --timeout modestly.",
    "rate_limited": "Server asked us to slow down (429/Retry-After). Wait, then re-run with a larger --interval.",
    "server_error": "Server returned 5xx after retries. Re-run later.",
    "http_error": "Non-retryable HTTP status. Check the URL/endpoint against the current API docs.",
    "not_found": "Endpoint or object not found (404). Check the endpoint path against the current API docs.",
    "invalid_json": "Response was not JSON. Inspect the saved snapshot/log; the endpoint may have changed.",
    "unexpected_schema": "JSON lacked expected fields. Re-check the API documentation for the response format.",
    "not_an_image": "Server returned non-image content (e.g. an HTML error page). Retry later; do not save.",
    "empty_file": "Zero-byte response. Retry later.",
    "too_large": "File exceeded the size cap. Raise --max-image-mb only if the larger file is needed.",
    "invalid_image": "Pillow could not fully decode the file (truncated/corrupt). Retry the download later.",
    "duplicate_hash": "Identical bytes already saved under another record; kept the first, skipped this one.",
    "host_not_allowed": "URL or redirect pointed outside the approved Met hosts; it was not followed.",
    "existing_file_conflict": "A file already exists at the target path and is not in the manifest. "
                              "Inspect it manually; the collector never overwrites it.",
    "classification_cap": "Variety heuristic skipped it; raise --per-class-cap to include more of one class.",
    "snapshot_missing": "Replay mode needs a saved snapshot for this request. Run live once first.",
    "manifest_write_failed": "Could not append to the manifest; the image file was removed to avoid an orphan.",
}


class FetchError(Exception):
    """A request or file-validation failure with a stable category."""

    def __init__(self, category: str, detail: str = "", status: "int | None" = None):
        super().__init__(f"{category}: {detail}")
        self.category = category
        self.detail = detail
        self.status = status


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- HTTP

@dataclass
class HttpResult:
    status: int
    headers: dict
    final_url: str
    body: bytes = b""
    bytes_written: int = 0


class _ApprovedHostRedirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only when the target is https on an approved Met host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlparse(newurl)
        if target.scheme != "https" or target.hostname not in ALLOWED_HOSTS:
            raise FetchError("host_not_allowed", f"refused redirect {code} to {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_opener():
    return urllib.request.build_opener(_ApprovedHostRedirects()).open


def require_host(url: str, hosts: frozenset) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in hosts:
        raise FetchError("host_not_allowed", f"{url} is not https on {sorted(hosts)}")


class HttpClient:
    """Sequential HTTP client: one request at a time, a minimum interval between
    requests, bounded retries that honour Retry-After, and no retry on policy denials."""

    def __init__(self, opener=None, min_interval: float = 1.0, timeout: float = 30.0,
                 max_retries: int = 2, max_retry_after: float = 60.0,
                 sleep=time.sleep, clock=time.monotonic, log: "logging.Logger | None" = None):
        if min_interval < MIN_REQUEST_INTERVAL:
            raise ValueError(f"min_interval must be >= {MIN_REQUEST_INTERVAL}s")
        self.opener = opener or default_opener()
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_retry_after = max_retry_after
        self.sleep = sleep
        self.clock = clock
        self.log = log or logging.getLogger("collector")
        self._last = None
        self.requests_made = {"api": 0, "image": 0}
        self.requests_failed = {"api": 0, "image": 0}

    def _throttle(self):
        if self._last is not None:
            wait = self.min_interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        self._last = self.clock()

    @staticmethod
    def _retry_after_seconds(value: "str | None") -> "float | None":
        if not value:
            return None
        value = value.strip()
        if value.isdigit():
            return float(value)
        try:
            when = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        return max(0.0, (when - dt.datetime.now(dt.timezone.utc)).total_seconds())

    def _request(self, url: str, accept: str, consume, kind: str):
        attempt = 0
        while True:
            attempt += 1
            self._throttle()
            self.requests_made[kind] += 1
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
            try:
                with self.opener(req, timeout=self.timeout) as resp:
                    status = getattr(resp, "status", None) or resp.getcode()
                    headers = {k.lower(): v for k, v in resp.headers.items()}
                    final_url = resp.geturl()
                    if status != 200:
                        raise FetchError("http_error", f"HTTP {status} for {url}", status)
                    return consume(resp, HttpResult(status, headers, final_url))
            except urllib.error.HTTPError as e:
                code = e.code
                retry_after = self._retry_after_seconds(e.headers.get("Retry-After") if e.headers else None)
                if code == 429 or code in (500, 502, 503, 504):
                    category = "rate_limited" if code == 429 else "server_error"
                    if attempt > self.max_retries:
                        self.requests_failed[kind] += 1
                        raise FetchError(category, f"HTTP {code} after {attempt} attempts: {url}", code)
                    if retry_after is not None and retry_after > self.max_retry_after:
                        self.requests_failed[kind] += 1
                        raise FetchError(category, f"HTTP {code}; Retry-After {retry_after:.0f}s exceeds "
                                                   f"the {self.max_retry_after:.0f}s cap: {url}", code)
                    delay = retry_after if retry_after is not None else 2.0 * (2 ** (attempt - 1))
                    self.log.warning("HTTP %s for %s; retry %d/%d in %.1fs", code, url, attempt,
                                     self.max_retries, delay)
                    self.sleep(delay)
                    continue
                self.requests_failed[kind] += 1
                raise FetchError("not_found" if code == 404 else "http_error", f"HTTP {code}: {url}", code)
            except FetchError:
                self.requests_failed[kind] += 1
                raise
            except urllib.error.URLError as e:
                reason = str(e.reason)
                if "Tunnel connection failed: 403" in reason or "Tunnel connection failed: 407" in reason:
                    # Policy denial: never retried, never routed around.
                    self.requests_failed[kind] += 1
                    raise FetchError("network_blocked", f"{reason} ({url})")
                category = "timeout" if "timed out" in reason.lower() else "network_error"
                if attempt > self.max_retries:
                    self.requests_failed[kind] += 1
                    raise FetchError(category, f"{reason} ({url})")
                self.sleep(2.0 * (2 ** (attempt - 1)))
            except (TimeoutError, OSError) as e:
                category = "timeout" if isinstance(e, TimeoutError) else "network_error"
                if attempt > self.max_retries:
                    self.requests_failed[kind] += 1
                    raise FetchError(category, f"{e} ({url})")
                self.sleep(2.0 * (2 ** (attempt - 1)))

    def get_json(self, url: str) -> "tuple[object, bytes]":
        require_host(url, OFFICIAL_API_HOSTS)
        def consume(resp, result):
            body = resp.read(MAX_JSON_BYTES + 1)
            if len(body) > MAX_JSON_BYTES:
                raise FetchError("too_large", f"JSON body exceeds {MAX_JSON_BYTES} bytes: {url}")
            result.body = body
            return result

        result = self._request(url, "application/json", consume, "api")
        try:
            return json.loads(result.body.decode("utf-8")), result.body
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            self.requests_failed["api"] += 1
            raise FetchError("invalid_json", f"{e.__class__.__name__} from {url}: "
                                             f"{result.body[:80]!r}")

    def download(self, url: str, fh, max_bytes: int, overall_timeout: float = 180.0) -> HttpResult:
        require_host(url, OFFICIAL_IMAGE_HOSTS)
        def consume(resp, result):
            length = result.headers.get("content-length")
            if length and length.isdigit() and int(length) > max_bytes:
                raise FetchError("too_large", f"Content-Length {length} > {max_bytes}")
            started = self.clock()
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                result.bytes_written += len(chunk)
                if result.bytes_written > max_bytes:
                    raise FetchError("too_large", f"body exceeded {max_bytes} bytes")
                if self.clock() - started > overall_timeout:
                    raise FetchError("timeout", f"download exceeded {overall_timeout}s")
                fh.write(chunk)
            if length and length.isdigit() and int(length) != result.bytes_written:
                raise FetchError("invalid_image", f"truncated transfer: Content-Length {length}, "
                                                  f"received {result.bytes_written}")
            return result

        return self._request(url, "image/*", consume, "image")


# --------------------------------------------------------------------------- API parsing

def parse_search_response(data) -> "list[int]":
    """Return objectIDs from a search response. ``objectIDs: null`` means no hits."""
    if not isinstance(data, dict) or "objectIDs" not in data:
        keys = sorted(data) if isinstance(data, dict) else type(data).__name__
        raise FetchError("unexpected_schema", f"search response lacks objectIDs (keys: {keys})")
    ids = data["objectIDs"]
    if ids is None:
        return []
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise FetchError("unexpected_schema", "objectIDs is not a list of integers")
    return ids


def plan_candidates(results: "dict[str, list[int]]", terms, per_term: int) -> "list[tuple[str, int]]":
    """Deterministic round-robin over terms, in API-returned order, first occurrence wins.

    Given the same saved search responses this always yields the same list, and
    interleaving terms keeps one term's near-identical hits from filling the pilot.
    """
    seen, plan = set(), []
    for rank in range(per_term):
        for term in terms:
            ids = results.get(term) or []
            if rank < len(ids) and ids[rank] not in seen:
                seen.add(ids[rank])
                plan.append((term, ids[rank]))
    return plan


def _clean(value):
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if value in ([], {}):
        return None
    return value


def check_eligibility(obj) -> "tuple[bool, str | None, str]":
    """Rights first, then image. Only a literal boolean ``True`` counts as public domain."""
    if not isinstance(obj, dict) or not isinstance(obj.get("objectID"), int):
        return False, "unexpected_schema", "object record lacks an integer objectID"
    flag = obj.get("isPublicDomain")
    if flag is not True:
        if flag is False:
            return False, "rights_not_public_domain", "isPublicDomain is false"
        return False, "rights_uncertain", f"isPublicDomain missing or non-boolean: {flag!r}"
    url = obj.get("primaryImage")
    if not isinstance(url, str) or not url.strip():
        return False, "image_url_missing", "primaryImage is empty or missing"
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_IMAGE_HOSTS:
        return False, "image_url_not_official", f"primaryImage host not in {sorted(OFFICIAL_IMAGE_HOSTS)}: {url}"
    return True, None, "isPublicDomain is true and primaryImage is an official Met image URL"


def near_duplicate_key(obj: dict) -> tuple:
    def norm(v):
        v = _clean(v)
        return unicodedata.normalize("NFKC", v).casefold() if isinstance(v, str) else None
    return (norm(obj.get("title")), norm(obj.get("artistDisplayName")), norm(obj.get("classification")))


def parse_bare_year(value) -> "int | None":
    """Only a date string that is exactly a year ("1893") yields a year. "ca. 1890",
    "1890-95", "19th century" stay null; the raw text is kept in creation_date_text."""
    value = _clean(value)
    if isinstance(value, str) and re.fullmatch(r"\d{3,4}", value):
        return int(value)
    return None


def build_record(obj: dict, *, local_file_path: str, sha256: str, file_size_bytes: int,
                 image_info: dict, collected_at: str, snapshot_path: str, snapshot_sha256: str,
                 search_term: str, search_endpoint: str) -> dict:
    """Map an official object record plus the actual download result to one manifest record.

    Source values are copied verbatim (null when absent); nothing is inferred.
    ``field_provenance`` says, for every field, whether it came from the API, from the
    pipeline, or from the rights policy. ``context_claims`` is always empty here.
    """
    oid = obj["objectID"]
    country_field = "country" if _clean(obj.get("country")) else ("region" if _clean(obj.get("region")) else None)
    object_date = _clean(obj.get("objectDate"))

    record = {
        "record_id": f"met:{oid}",
        "source_object_id": oid,
        "title": _clean(obj.get("title")),
        "creator": _clean(obj.get("artistDisplayName")),
        "creation_year": parse_bare_year(object_date),
        "creation_date_text": object_date,
        "publication_year": None,
        "country_or_region": _clean(obj.get(country_field)) if country_field else None,
        "genre": _clean(obj.get("classification")),
        "medium": _clean(obj.get("medium")),
        "source_institution": SOURCE_INSTITUTION,
        "source_record_url": _clean(obj.get("objectURL")),
        "api_record_url": OBJECT_URL.format(object_id=oid),
        "original_image_url": obj["primaryImage"].strip(),
        "local_file_path": local_file_path,
        "is_public_domain": obj.get("isPublicDomain") is True,
        "license": LICENSE_ID,
        "license_evidence_url": RIGHTS_POLICY_URL,
        "rights_evidence": {
            # Object-level fact, read from this object's API record:
            "api_field": "isPublicDomain",
            "api_value": obj.get("isPublicDomain"),
            "api_record_url": OBJECT_URL.format(object_id=oid),
            # General statement, not an object-level field:
            "license_basis": "general_policy_statement",
            "policy_url": RIGHTS_POLICY_URL,
            "scope": "The API returns no per-object license string. CC0 is taken from The Met's "
                     "Open Access policy for images of public-domain works, and applies only to this "
                     "object's primaryImage; not generalised to other images or third-party material.",
            "checked_at": collected_at,
        },
        "attribution_text": None,
        "collected_at": collected_at,
        "sha256": sha256,
        "file_size_bytes": file_size_bytes,
        "image_validation_status": "valid",
        "image_format": image_info.get("format"),
        "image_width": image_info.get("width"),
        "image_height": image_info.get("height"),
        "metadata_snapshot_path": snapshot_path,
        "metadata_snapshot_sha256": snapshot_sha256,
        "selection": {"search_term": search_term, "search_endpoint": search_endpoint},
        "metadata_confidence": None,
        "context_claims": [],
    }
    record["attribution_text"] = attribution_text(obj, record)
    missing = [f for f in REQUIRED_FIELDS if record.get(f) is None and f not in ("metadata_confidence",)]
    record["metadata_confidence"] = {
        "level": "source_reported",
        "basis": "Descriptive values are copied verbatim from the official Met object record; none are inferred.",
        "missing_fields": missing,
        "notes": {
            "genre": "Met 'classification' used as a genre proxy; it is the museum's cataloguing class, not a genre judgement.",
            "creation_year": "Set only when Met 'objectDate' is a bare year; otherwise null with the raw text in creation_date_text.",
            "publication_year": "The object API has no publication-date field; left null.",
        },
    }
    record["field_provenance"] = {
        "record_id": "pipeline (from api:objectID)",
        "title": "api:title",
        "creator": "api:artistDisplayName",
        "creation_year": "api:objectDate (bare year only)",
        "creation_date_text": "api:objectDate",
        "publication_year": "not_provided_by_source",
        "country_or_region": f"api:{country_field}" if country_field else "not_provided_by_source",
        "genre": "api:classification",
        "medium": "api:medium",
        "source_institution": "fixed",
        "source_record_url": "api:objectURL",
        "original_image_url": "api:primaryImage",
        "is_public_domain": "api:isPublicDomain",
        "license": "policy:" + RIGHTS_POLICY_URL,
        "license_evidence_url": "policy",
        "attribution_text": "pipeline (assembled from api fields)",
        "collected_at": "pipeline",
        "local_file_path": "pipeline",
        "sha256": "pipeline (computed from saved file)",
        "file_size_bytes": "pipeline (saved file)",
        "image_validation_status": "pipeline (Pillow decode)",
        "metadata_confidence": "pipeline",
        "context_claims": "none (no cited interpretation added)",
    }
    return record


def attribution_text(obj: dict, record: dict) -> str:
    head = ", ".join(v for v in (record["title"], record["creator"], record["creation_date_text"]) if v)
    parts = [head] if head else []
    credit = _clean(obj.get("creditLine"))
    parts.append(SOURCE_INSTITUTION + (f", {credit}" if credit else ""))
    parts.append(f"Object {obj['objectID']}")
    parts.append("Public domain image (CC0 1.0) via The Met Open Access")
    return ". ".join(parts) + "."


# --------------------------------------------------------------------------- files

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def looks_like_markup(head: bytes) -> bool:
    head = head.lstrip().lower()
    return head.startswith((b"<!doctype", b"<html", b"<?xml", b"<head", b"<body", b"{", b"["))


def signature_check(path: Path) -> dict:
    """Standard-library check of magic bytes (and the end marker for JPEG/PNG).

    PRELIMINARY ONLY: a matching signature does not prove the pixel data decodes.
    It is reported separately and is never treated as equivalent to ``inspect_image``.
    """
    size = path.stat().st_size
    with open(path, "rb") as fh:
        head = fh.read(16)
        fh.seek(max(0, size - 16))
        tail = fh.read(16)
    fmt, end_ok = None, None
    if head.startswith(b"\xff\xd8\xff"):
        fmt, end_ok = "JPEG", tail.rstrip(b"\x00").endswith(b"\xff\xd9")
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        fmt, end_ok = "PNG", b"IEND" in tail
    elif head[:6] in (b"GIF87a", b"GIF89a"):
        fmt, end_ok = "GIF", tail.endswith(b";")
    elif head[:4] in (b"II*\x00", b"MM\x00*"):
        fmt = "TIFF"
    elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        fmt = "WEBP"
    return {"signature_format": fmt, "end_marker_ok": end_ok, "size": size,
            "note": "magic-byte check only; not equivalent to full image decoding"}


def inspect_image(path: Path) -> dict:
    """Fully decode the file. ``verify()`` alone does not catch truncated pixel data."""
    if Image is None:
        raise FetchError("invalid_image", "Pillow is not installed; cannot validate images")
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            im.load()
            return {"format": im.format, "width": im.width, "height": im.height}
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as e:
        raise FetchError("invalid_image", f"{e.__class__.__name__}: {e}")


def place_without_overwrite(tmp: Path, final: Path) -> None:
    """Atomically move ``tmp`` to ``final``; fail if ``final`` already exists."""
    try:
        os.link(tmp, final)
    except FileExistsError:
        raise FetchError("existing_file_conflict", f"{final} already exists; not overwritten")
    except OSError:
        # Filesystem without hard links: reserve the name exclusively, then replace.
        try:
            fd = os.open(final, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            raise FetchError("existing_file_conflict", f"{final} already exists; not overwritten")
        os.close(fd)
        os.replace(tmp, final)
        return
    os.unlink(tmp)


def safe_image_filename(object_id, image_format: str) -> str:
    """``met_<objectID><ext>``. Only a positive int ID and a known Pillow format are accepted,
    so no API-supplied text ever reaches the filesystem path."""
    if not isinstance(object_id, int) or isinstance(object_id, bool) or object_id <= 0:
        raise ValueError(f"object id must be a positive int, got {object_id!r}")
    ext = IMAGE_FORMAT_EXT.get(image_format)
    if ext is None:
        raise ValueError(f"unsupported image format {image_format!r}")
    return f"met_{object_id}{ext}"


def existing_files_for(images_dir: Path, object_id: int) -> "list[Path]":
    return sorted(images_dir.glob(f"met_{object_id}.*"))


def download_image(client: HttpClient, url: str, images_dir: Path, object_id: int,
                   known_hashes: "dict[str, str]", max_bytes: int = MAX_IMAGE_BYTES) -> dict:
    """Download to a temp file, validate, de-duplicate by SHA-256, then place atomically."""
    images_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".tmp-met_{object_id}-", suffix=".part", dir=images_dir)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            result = client.download(url, fh, max_bytes)
            fh.flush()
            os.fsync(fh.fileno())
        final_host = urllib.parse.urlparse(result.final_url).hostname
        if final_host not in OFFICIAL_IMAGE_HOSTS:
            raise FetchError("image_url_not_official", f"redirected to non-official host {final_host}")
        ctype = (result.headers.get("content-type") or "").split(";")[0].strip().lower()
        size = tmp.stat().st_size
        if size == 0:
            raise FetchError("empty_file", f"0 bytes from {url}")
        with open(tmp, "rb") as fh:
            head = fh.read(512)
        if not ctype.startswith("image/") or looks_like_markup(head):
            raise FetchError("not_an_image", f"Content-Type {ctype or 'missing'!r}; first bytes {head[:24]!r}")
        sig = signature_check(tmp)
        info = inspect_image(tmp)
        if sig["signature_format"] != info["format"] or sig["end_marker_ok"] is False:
            raise FetchError("invalid_image", f"signature {sig['signature_format']} "
                                              f"(end marker ok: {sig['end_marker_ok']}) vs decoded {info['format']}")
        try:
            name = safe_image_filename(object_id, info["format"])
        except ValueError as e:
            raise FetchError("invalid_image", str(e))
        digest = sha256_file(tmp)
        if digest in known_hashes:
            raise FetchError("duplicate_hash", f"same SHA-256 as {known_hashes[digest]}")
        final = images_dir / name
        place_without_overwrite(tmp, final)
        return {"path": final, "sha256": digest, "size": size, "image_info": info,
                "content_type": ctype, "final_url": result.final_url}
    finally:
        if tmp.exists():
            tmp.unlink()


# --------------------------------------------------------------------------- manifest

def read_manifest(path: Path) -> "list[dict]":
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if line.strip():
                rec = json.loads(line)
                if not isinstance(rec, dict):
                    raise ValueError(f"{path}:{n}: not a JSON object")
                records.append(rec)
    return records


def append_manifest(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=False)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# --------------------------------------------------------------------------- snapshots

class SnapshotStore:
    """Saves every API response byte-for-byte under metadata/api_snapshots/<run_id>/.

    In replay mode it serves those saved bytes instead of the network, so the same
    saved responses reproduce the same selection.
    """

    def __init__(self, root: Path, run_id: str, replay: bool = False):
        self.root = root
        self.run_id = run_id
        self.dir = root / run_id
        self.replay = replay
        if replay and not self.dir.is_dir():
            raise FileNotFoundError(f"no saved snapshots at {self.dir}")

    @staticmethod
    def _safe(name: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", name)

    def path_for(self, kind: str, key: str) -> Path:
        return self.dir / kind / f"{self._safe(key)}.json"

    def load(self, kind: str, key: str) -> "tuple[object, bytes] | None":
        p = self.path_for(kind, key)
        if not p.exists():
            return None
        raw = p.read_bytes()
        return json.loads(raw.decode("utf-8")), raw

    def save(self, kind: str, key: str, raw: bytes) -> Path:
        p = self.path_for(kind, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "xb") as fh:  # never overwrite a saved response
            fh.write(raw)
        return p


# --------------------------------------------------------------------------- run

@dataclass
class RunStats:
    run_id: str
    started_at: str
    mode: str
    terms: list
    seed_objects: list = field(default_factory=list)
    finished_at: "str | None" = None
    status: str = "running"
    search_hits: dict = field(default_factory=dict)
    candidates_planned: int = 0
    api_requests: int = 0
    api_requests_failed: int = 0
    image_requests: int = 0
    image_requests_failed: int = 0
    snapshot_run_id: "str | None" = None
    decisions: list = field(default_factory=list)
    records_inspected: int = 0
    eligible: int = 0
    excluded: dict = field(default_factory=dict)
    already_in_manifest: int = 0
    downloads_attempted: int = 0
    transfers_completed: int = 0
    downloaded: int = 0
    file_validation_passed: int = 0
    duplicates: int = 0
    failures: list = field(default_factory=list)
    missing_fields: dict = field(default_factory=dict)
    new_records: list = field(default_factory=list)

    def exclude(self, reason: str):
        self.excluded[reason] = self.excluded.get(reason, 0) + 1

    def fail(self, category: str, detail: str, record_id: "str | None" = None, url: "str | None" = None):
        self.failures.append({"category": category, "record_id": record_id, "url": url, "detail": detail,
                              "remediation": REMEDIATION.get(category, "See logs/collection.log.")})


# Failures that happen after the bytes arrived (the transfer itself completed).
TRANSFER_DONE_CATEGORIES = frozenset({"not_an_image", "empty_file", "invalid_image", "duplicate_hash",
                                      "existing_file_conflict", "image_url_not_official"})


class Collector:
    def __init__(self, archive_dir: Path, client: HttpClient, terms=DEFAULT_TERMS, max_images: int = 10,
                 per_term: int = 8, max_inspect: int = 40, replay_run: "str | None" = None,
                 plan_only: bool = False, log: "logging.Logger | None" = None,
                 max_image_bytes: int = MAX_IMAGE_BYTES, seed_objects=DEFAULT_SEED_OBJECTS,
                 per_class_cap: int = 3):
        if not 1 <= max_images <= HARD_MAX_IMAGES:
            raise ValueError(f"max_images must be within 1..{HARD_MAX_IMAGES}")
        self.dir = archive_dir
        self.images = archive_dir / "images"
        self.manifest = archive_dir / "manifests" / "collection_manifest.jsonl"
        self.client = client
        self.terms = list(terms)
        self.max_images = max_images
        self.per_term = per_term
        self.max_inspect = max_inspect
        self.plan_only = plan_only
        self.max_image_bytes = max_image_bytes
        self.seed_objects = [int(o) for o in seed_objects]
        self.per_class_cap = per_class_cap
        self.log = log or logging.getLogger("collector")
        now_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snap_root = archive_dir / "metadata" / "api_snapshots"
        if not replay_run:  # two runs in the same second must not share (or clobber) a snapshot dir
            base, n = now_id, 1
            while (snap_root / now_id).exists():
                n += 1
                now_id = f"{base}-{n}"
        snapshot_id = replay_run or now_id
        self.snapshots = SnapshotStore(snap_root, snapshot_id, replay=bool(replay_run))
        # A replay gets its own run id so it can never overwrite the live run's report.
        self.stats = RunStats(run_id=f"{now_id}-replay-of-{replay_run}" if replay_run else now_id,
                              started_at=utc_now(),
                              mode="replay" if replay_run else ("plan-only" if plan_only else "live"),
                              terms=self.terms, snapshot_run_id=snapshot_id, seed_objects=self.seed_objects)

    # -- API with snapshotting
    def _api_json(self, kind: str, key: str, url: str):
        if self.snapshots.replay:
            hit = self.snapshots.load(kind, key)
            if hit is None:
                raise FetchError("snapshot_missing", f"{kind}/{key}")
            return hit[0], self.snapshots.path_for(kind, key), hashlib.sha256(hit[1]).hexdigest()
        data, raw = self.client.get_json(url)
        path = self.snapshots.save(kind, key, raw)
        return data, path, hashlib.sha256(raw).hexdigest()

    def _process(self, term: str, oid: int) -> None:
        """Inspect one object and, if eligible, download, validate and record it."""
        s = self.stats
        record_id = f"met:{oid}"
        object_url = OBJECT_URL.format(object_id=oid)
        try:
            obj, snap_path, snap_sha = self._api_json("objects", str(oid), object_url)
        except FetchError as e:
            s.api_requests_failed += 1
            s.decisions.append([term, oid, "fetch_failed:" + e.category])
            s.fail(e.category, e.detail, record_id=record_id, url=object_url)
            self.log.error("object %s failed: %s", oid, e)
            self._blocked = e.category in ("network_blocked", "host_not_allowed")
            return
        s.records_inspected += 1
        ok, reason, detail = check_eligibility(obj)
        if ok and obj.get("objectID") != oid:
            ok, reason, detail = False, "unexpected_schema", f"asked for {oid}, got objectID {obj.get('objectID')}"
        if not ok:
            s.decisions.append([term, oid, reason])
            s.exclude(reason)
            self.log.info("exclude %s: %s (%s)", record_id, reason, detail)
            return
        key = near_duplicate_key(obj)
        if key in self._seen_keys:
            s.decisions.append([term, oid, "near_duplicate_metadata"])
            s.exclude("near_duplicate_metadata")
            self.log.info("exclude %s: near-duplicate metadata %s", record_id, key)
            return
        cls = key[2]
        if term != "seed" and self.per_class_cap and self._per_class.get(cls, 0) >= self.per_class_cap:
            s.decisions.append([term, oid, "classification_cap"])
            s.exclude("classification_cap")
            self.log.info("exclude %s: classification %r already has %d picks", record_id, cls, self.per_class_cap)
            return
        self._seen_keys.add(key)
        s.eligible += 1
        s.decisions.append([term, oid, "eligible"])
        if record_id in self._in_manifest:
            s.already_in_manifest += 1
            self._per_class[cls] = self._per_class.get(cls, 0) + 1
            self.log.info("skip %s: already in manifest", record_id)
            return
        if self.plan_only:
            self._per_class[cls] = self._per_class.get(cls, 0) + 1
            return
        clash = existing_files_for(self.images, oid)
        if clash:
            s.fail("existing_file_conflict", f"{clash[0].name} exists but is not in the manifest", record_id)
            self.log.error("skip %s: existing file %s not in manifest; not overwritten", record_id, clash[0])
            return
        s.downloads_attempted += 1
        url = obj["primaryImage"].strip()
        try:
            got = download_image(self.client, url, self.images, oid, self._known_hashes, self.max_image_bytes)
        except FetchError as e:
            if e.category in TRANSFER_DONE_CATEGORIES:
                s.transfers_completed += 1
            if e.category == "duplicate_hash":
                s.duplicates += 1
                s.file_validation_passed += 1
            s.fail(e.category, e.detail, record_id=record_id, url=url)
            self.log.error("download %s failed: %s", record_id, e)
            self._blocked = e.category in ("network_blocked",)
            return
        s.transfers_completed += 1
        s.file_validation_passed += 1
        # Reconcile: re-read the placed file and require the same hash before writing metadata.
        if sha256_file(got["path"]) != got["sha256"]:
            got["path"].unlink()
            s.fail("invalid_image", "hash changed after placement", record_id, url)
            return
        record = build_record(
            obj,
            local_file_path=got["path"].relative_to(self.dir).as_posix(),
            sha256=got["sha256"], file_size_bytes=got["size"], image_info=got["image_info"],
            collected_at=utc_now(), snapshot_path=Path(snap_path).relative_to(self.dir).as_posix(),
            snapshot_sha256=snap_sha, search_term=term, search_endpoint="seed" if term == "seed" else "v1/search",
        )
        try:
            append_manifest(self.manifest, record)
        except OSError as e:
            got["path"].unlink()
            s.fail("manifest_write_failed", str(e), record_id, url)
            return
        s.downloaded += 1
        self._known_hashes[got["sha256"]] = record_id
        self._in_manifest.add(record_id)
        self._per_class[cls] = self._per_class.get(cls, 0) + 1
        for f in record["metadata_confidence"]["missing_fields"]:
            s.missing_fields[f] = s.missing_fields.get(f, 0) + 1
        s.new_records.append(record_id)
        self.log.info("saved %s -> %s (%d bytes, sha256 %s)", record_id, record["local_file_path"],
                      got["size"], got["sha256"][:12])

    def search(self, term: str) -> "list[int]":
        query = urllib.parse.urlencode({"q": term, "hasImages": "true"})
        data, _, _ = self._api_json("search", term, f"{SEARCH_URL}?{query}")
        ids = parse_search_response(data)
        self.log.info("search %r: %d ids (response keys: %s)", term, len(ids),
                      sorted(data) if isinstance(data, dict) else "-")
        return ids

    def run(self) -> RunStats:
        s = self.stats
        self.log.info("run %s start mode=%s seeds=%s terms=%s max_images=%d", s.run_id, s.mode,
                      self.seed_objects, self.terms, self.max_images)
        existing = read_manifest(self.manifest)
        self._in_manifest = {r.get("record_id") for r in existing}
        self._known_hashes = {r["sha256"]: r["record_id"] for r in existing if r.get("sha256")}
        self._seen_keys = set()
        self._per_class = {}
        self._blocked = False

        # 1. Known seed objects first (e.g. 436121), so the whole path is proven on a known record.
        for oid in self.seed_objects:
            if self._blocked or s.downloaded >= self.max_images:
                break
            self._process("seed", oid)

        # 2. Bounded search, deterministic round-robin plan.
        results = {}
        for term in self.terms:
            if self._blocked or s.downloaded >= self.max_images:
                break
            try:
                results[term] = self.search(term)
                s.search_hits[term] = len(results[term])
            except FetchError as e:
                s.api_requests_failed += 1
                s.fail(e.category, e.detail, url=f"search:{term}")
                self.log.error("search %r failed: %s", term, e)
                if e.category in ("network_blocked", "host_not_allowed"):
                    self._blocked = True  # same host for every term; do not hammer a denied proxy
        plan = [c for c in plan_candidates(results, self.terms, self.per_term) if c[1] not in self.seed_objects]
        plan = plan[: max(0, self.max_inspect - len(self.seed_objects))]
        s.candidates_planned = len(plan) + len(self.seed_objects)
        self.log.info("planned %d search candidates", len(plan))
        for term, oid in plan:
            if self._blocked or s.downloaded >= self.max_images:
                break
            self._process(term, oid)

        s.api_requests = self.client.requests_made["api"]
        s.image_requests = self.client.requests_made["image"]
        s.image_requests_failed = self.client.requests_failed["image"]
        blocked = any(f["category"] == "network_blocked" for f in s.failures)
        if s.downloaded:
            s.status = "completed"
        elif blocked:
            s.status = "blocked"
        elif self.plan_only:
            s.status = "planned"
        else:
            s.status = "no_images"
        s.finished_at = utc_now()
        self.log.info("run %s end status=%s downloaded=%d", s.run_id, s.status, s.downloaded)
        return s


# --------------------------------------------------------------------------- report

def write_reports(archive_dir: Path, stats: RunStats) -> Path:
    reports = archive_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    runs_dir = reports / "runs"
    runs_dir.mkdir(exist_ok=True)
    (runs_dir / f"collection_run_{stats.run_id}.json").write_text(
        json.dumps(stats.__dict__, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = archive_dir / "manifests" / "collection_manifest.jsonl"
    try:
        total_records = len(read_manifest(manifest))
    except (ValueError, json.JSONDecodeError):
        total_records = "unreadable (see validate_collection.py)"

    excl = stats.excluded
    lines = [
        "# Collection Report",
        "",
        f"Generated by `collector.py` at {stats.finished_at}. Every number below is counted by the "
        "collector during this run; nothing is estimated.",
        "",
        "## Run",
        "",
        f"- Run ID: `{stats.run_id}` (API snapshots: `metadata/api_snapshots/{stats.snapshot_run_id}/`)",
        f"- Mode: `{stats.mode}`",
        f"- Status: **{stats.status}**",
        f"- Started / finished (UTC): {stats.started_at} / {stats.finished_at}",
        f"- Seed objects (processed first): {stats.seed_objects}",
        f"- Search terms: {', '.join(stats.terms)} (endpoint `/public/collection/v1/search`, `hasImages=true`)",
        f"- Searches completed: {len(stats.search_hits)} of {len(stats.terms)}"
        + ("" if len(stats.search_hits) == len(stats.terms) else
           " (search stops early once the image limit is reached or a host is blocked)"),
        f"- Search hits per term: {stats.search_hits or 'none'}",
        f"- Manifest records in total after this run: {total_records}",
        "",
        "## Counts (this run)",
        "",
        "| Measure | Count |",
        "|---|---|",
        f"| API requests made (search + object) | {stats.api_requests} |",
        f"| API requests that ended in failure (search/object, after retries) | {stats.api_requests_failed} |",
        f"| Image download requests (incl. retries) | {stats.image_requests} |",
        f"| Image download attempts (records) | {stats.downloads_attempted} |",
        f"| Candidates planned (seed objects + search picks) | {stats.candidates_planned} |",
        f"| API object records inspected | {stats.records_inspected} |",
        f"| Records eligible for download | {stats.eligible} |",
        f"| Eligible but already in manifest (skipped) | {stats.already_in_manifest} |",
        f"| Image transfers completed (bytes received) | {stats.transfers_completed} |",
        f"| Images that passed file validation (Pillow full decode) | {stats.file_validation_passed} |",
        f"| **Images saved with a manifest record** (successful images) | **{stats.downloaded}** |",
        f"| Duplicate files (same SHA-256) | {stats.duplicates} |",
        f"| Failed requests / downloads | {len(stats.failures)} |",
        f"| Excluded: rights uncertain (isPublicDomain missing/non-boolean) | {excl.get('rights_uncertain', 0)} |",
        f"| Excluded: not public domain (isPublicDomain false) | {excl.get('rights_not_public_domain', 0)} |",
        f"| Excluded: primaryImage missing | {excl.get('image_url_missing', 0)} |",
        f"| Excluded: primaryImage not an official Met URL | {excl.get('image_url_not_official', 0)} |",
        f"| Excluded: near-duplicate metadata | {excl.get('near_duplicate_metadata', 0)} |",
        f"| Excluded: classification cap (variety heuristic) | {excl.get('classification_cap', 0)} |",
        f"| Excluded: unexpected record schema | {excl.get('unexpected_schema', 0)} |",
        "",
        "## Missing metadata fields (records saved this run)",
        "",
    ]
    if stats.missing_fields:
        lines += ["| Field | Records with null |", "|---|---|"]
        lines += [f"| `{k}` | {v} |" for k, v in sorted(stats.missing_fields.items())]
    else:
        lines.append("No records were saved in this run, so there are no missing-field counts."
                     if not stats.new_records else "No required field was null.")
    lines += ["", "## Failures", ""]
    if stats.failures:
        lines += ["| Category | Record | Target | Detail | Remediation |", "|---|---|---|---|---|"]
        for f in stats.failures:
            detail = str(f["detail"]).replace("|", "\\|")[:200]
            lines.append(f"| {f['category']} | {f['record_id'] or '-'} | {f['url'] or '-'} | {detail} | "
                         f"{f['remediation']} |")
    else:
        lines.append("None.")
    lines += [
        "",
        "## Observations, interpretations, assumptions",
        "",
        "**Observed (this run):** the counts and failures above, the HTTP outcomes in "
        "`logs/collection.log`, and the API responses saved under "
        f"`metadata/api_snapshots/{stats.snapshot_run_id}/`.",
        "",
        "**Interpretation:** a record is treated as CC0 because (a) its API record has "
        "`isPublicDomain: true` and (b) The Met's Open Access policy "
        f"({RIGHTS_POLICY_URL}) says images of public-domain works are released under CC0. "
        "This links two official statements; the API does not return a per-object license string.",
        "",
        "**Unverified assumptions:** see `KNOWN_ISSUES.md`. These include whether the search "
        "result order is stable over time, whether `classification` is a reasonable genre proxy, "
        "and whether a per-classification cap yields visual variety (it is a heuristic only).",
        "",
        "This is a pipeline-validation sample. It does not represent visual culture as a whole, "
        "the five search terms, or The Met's collection.",
        "",
    ]
    # Only a live run owns COLLECTION_REPORT.md; replays and plan-only runs report beside their JSON.
    path = reports / "COLLECTION_REPORT.md" if stats.mode == "live" else runs_dir / f"collection_report_{stats.run_id}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def setup_logging(archive_dir: Path) -> logging.Logger:
    logs = archive_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("collector")
    log.setLevel(logging.INFO)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S%z")
        fh = logging.FileHandler(logs / "collection.log", encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        log.addHandler(fh)
        log.addHandler(sh)
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive-dir", type=Path, default=ARCHIVE_DIR)
    ap.add_argument("--terms", nargs="+", default=list(DEFAULT_TERMS))
    ap.add_argument("--seed-objects", nargs="*", type=int, default=list(DEFAULT_SEED_OBJECTS),
                    help="object IDs processed before searching (default: 436121)")
    ap.add_argument("--per-class-cap", type=int, default=3, help="max picks per Met classification (0 = no cap)")
    ap.add_argument("--max-images", type=int, default=10, help=f"1..{HARD_MAX_IMAGES}")
    ap.add_argument("--per-term", type=int, default=8, help="candidates taken from each term's results")
    ap.add_argument("--max-inspect", type=int, default=40, help="upper bound on object-detail requests")
    ap.add_argument("--interval", type=float, default=1.0, help=f"seconds between requests (>= {MIN_REQUEST_INTERVAL})")
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--max-image-mb", type=float, default=MAX_IMAGE_BYTES / 1024 / 1024)
    ap.add_argument("--replay", metavar="RUN_ID", help="use saved API snapshots of RUN_ID instead of the network")
    ap.add_argument("--plan-only", action="store_true", help="select candidates but download nothing")
    args = ap.parse_args(argv)

    if Image is None:
        print("Pillow is required for image validation: pip install -r requirements.txt", file=sys.stderr)
        return 2
    if not 1 <= args.max_images <= HARD_MAX_IMAGES:
        ap.error(f"--max-images must be 1..{HARD_MAX_IMAGES}")
    archive = args.archive_dir.resolve()
    for sub in ("images", "metadata", "manifests", "logs", "reports"):
        (archive / sub).mkdir(parents=True, exist_ok=True)
    log = setup_logging(archive)
    client = HttpClient(min_interval=args.interval, timeout=args.timeout, log=log)
    collector = Collector(archive, client, terms=args.terms, max_images=args.max_images,
                          per_term=args.per_term, max_inspect=args.max_inspect, replay_run=args.replay,
                          plan_only=args.plan_only or bool(args.replay), log=log,
                          max_image_bytes=int(args.max_image_mb * 1024 * 1024),
                          seed_objects=args.seed_objects, per_class_cap=args.per_class_cap)
    stats = collector.run()
    report = write_reports(archive, stats)
    print(json.dumps({"run_id": stats.run_id, "status": stats.status, "downloaded": stats.downloaded,
                      "failures": len(stats.failures), "report": str(report)}, ensure_ascii=False))
    return {"completed": 0, "planned": 0}.get(stats.status, 1)


if __name__ == "__main__":
    sys.exit(main())
