"""Image format sniffing and measurement from bytes.

`sniff_format` decides the real format from magic bytes -- never from the URL
or the Content-Type header. `dimensions` reads width/height from the header
bytes (PNG, JPEG, GIF, WebP) without decoding pixels. `dominant_colors` needs
Pillow and a fully downloaded file; without it the feature stays unverified.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

FORMATS = {
    "png": ("image/png", "png"),
    "jpeg": ("image/jpeg", "jpg"),
    "gif": ("image/gif", "gif"),
    "webp": ("image/webp", "webp"),
}
SUPPORTED_MIME = {mime for mime, _ in FORMATS.values()}
MIME_ALIASES = {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg", "image/x-png": "image/png"}


def sniff_format(head: bytes) -> str | None:
    """Return 'png' | 'jpeg' | 'gif' | 'webp' | 'html' | None (unknown)."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    probe = head[:512].lstrip().lower()
    if probe.startswith((b"<!doctype html", b"<html", b"<head", b"<body", b"<?xml", b"<svg", b"{", b"[")):
        return "html" if not probe.startswith((b"{", b"[")) else "json"
    return None


def looks_complete(fmt: str, head: bytes, tail: bytes, size: int) -> bool:
    """Structural end-of-file check (detects truncated bodies without decoding)."""
    if fmt == "png":
        return tail.endswith(b"IEND\xaeB`\x82")
    if fmt == "jpeg":
        return tail.rstrip(b"\x00\r\n ").endswith(b"\xff\xd9")
    if fmt == "gif":
        return tail.rstrip(b"\x00").endswith(b"\x3b")
    if fmt == "webp":
        return len(head) >= 8 and int.from_bytes(head[4:8], "little") + 8 <= size
    return False


def normalize_mime(content_type: str | None) -> str | None:
    if not content_type:
        return None
    mime = content_type.split(";")[0].strip().lower()
    return MIME_ALIASES.get(mime, mime) or None


@dataclass
class Dimensions:
    width: int
    height: int


def dimensions(head: bytes) -> Dimensions | None:
    fmt = sniff_format(head)
    try:
        if fmt == "png" and len(head) >= 24 and head[12:16] == b"IHDR":
            w, h = struct.unpack(">II", head[16:24])
            return Dimensions(w, h) if w and h else None
        if fmt == "gif" and len(head) >= 10:
            w, h = struct.unpack("<HH", head[6:10])
            return Dimensions(w, h) if w and h else None
        if fmt == "webp":
            return _webp_dimensions(head)
        if fmt == "jpeg":
            return _jpeg_dimensions(head)
    except struct.error:
        return None
    return None


def _webp_dimensions(b: bytes) -> Dimensions | None:
    chunk = b[12:16]
    if chunk == b"VP8 " and len(b) >= 30:
        w, h = struct.unpack("<HH", b[26:30])
        return Dimensions(w & 0x3FFF, h & 0x3FFF)
    if chunk == b"VP8L" and len(b) >= 25:
        bits = int.from_bytes(b[21:25], "little")
        return Dimensions((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    if chunk == b"VP8X" and len(b) >= 30:
        w = int.from_bytes(b[24:27], "little") + 1
        h = int.from_bytes(b[27:30], "little") + 1
        return Dimensions(w, h)
    return None


_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_dimensions(b: bytes) -> Dimensions | None:
    i = 2
    n = len(b)
    while i + 4 <= n:
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
            i += 1 if marker == 0xFF else 2
            continue
        if marker in (0xD9, 0xDA):  # EOI / start of scan: no SOF before pixel data
            return None
        seg_len = struct.unpack(">H", b[i + 2:i + 4])[0]
        if marker in _SOF and i + 9 <= n:
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return Dimensions(w, h) if w and h else None
        i += 2 + seg_len
    return None


def aspect_ratio(width: int | None, height: int | None) -> dict | None:
    if not width or not height:
        return None
    ratio = round(width / height, 4)
    orientation = "landscape" if ratio > 1.05 else "portrait" if ratio < 0.95 else "square"
    return {"width": width, "height": height, "ratio": ratio, "orientation": orientation}


def pillow_available() -> bool:
    try:
        import PIL.Image  # noqa: F401
        return True
    except ImportError:
        return False


def verify_with_pillow(path) -> str | None:
    """Return None if Pillow can parse the file (or Pillow is absent), else an error string."""
    if not pillow_available():
        return None
    from PIL import Image
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:      # verify() does not decode; load() catches truncation
            im.load()
    except Exception as exc:  # noqa: BLE001 -- any decoder failure means "corrupt"
        return f"{type(exc).__name__}: {exc}"
    return None


def dominant_colors(data_or_path, count: int = 3) -> list[dict] | None:
    """Most frequent colours after quantization; None if Pillow is unavailable."""
    if not pillow_available():
        return None
    import io

    from PIL import Image
    src = io.BytesIO(data_or_path) if isinstance(data_or_path, (bytes, bytearray)) else data_or_path
    with Image.open(src) as im:
        im = im.convert("RGB")
        im.thumbnail((64, 64))
        quant = im.quantize(colors=max(count, 2), method=Image.Quantize.MEDIANCUT)
        palette = quant.getpalette() or []
        counts = sorted(quant.getcolors() or [], reverse=True)
        total = sum(c for c, _ in counts) or 1
        out = []
        for c, idx in counts[:count]:
            r, g, b = palette[idx * 3:idx * 3 + 3]
            out.append({"hex": f"#{r:02x}{g:02x}{b:02x}", "share": round(c / total, 3)})
        return out
