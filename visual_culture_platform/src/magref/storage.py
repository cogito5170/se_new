"""Local storage layout for downloaded image files.

    <data_root>/
        images/<publisher_slug>/<YYYY>/<sha256[:2]>/<sha256>.<ext>
        thumbnails/<sha256[:2]>/<sha256>.jpg   (Pillow only; regenerated on demand)
        tmp/                       partial downloads (*.part), never final files
        manifests/pending/         write-ahead journal: file moved, DB not yet committed
        quarantine/duplicates/     duplicate copies moved aside by `deduplicate --apply`
        exports/  logs/  database/

File names are built ONLY from the content hash and the sniffed format; the
publisher slug is reduced to [a-z0-9-]. Nothing from a URL or from page
metadata becomes part of a path verbatim, and every final path is checked to
resolve inside the images directory.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
EXT_RE = re.compile(r"^(png|jpg|gif|webp)$")


class StorageError(Exception):
    pass


def slugify(text: str | None, fallback: str = "unknown") -> str:
    if not text:
        return fallback
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:40].strip("-")
    return slug or fallback


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                return h.hexdigest()
            h.update(block)


@dataclass
class Layout:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root).expanduser().resolve()

    @property
    def images(self) -> Path:
        return self.root / "images"

    @property
    def thumbnails(self) -> Path:
        return self.root / "thumbnails"

    @property
    def tmp(self) -> Path:
        return self.root / "tmp"

    @property
    def journal(self) -> Path:
        return self.root / "manifests" / "pending"

    @property
    def quarantine(self) -> Path:
        return self.root / "quarantine" / "duplicates"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def database(self) -> Path:
        return self.root / "database" / "references.sqlite3"

    def ensure(self) -> None:
        for d in (self.images, self.thumbnails, self.tmp, self.journal, self.quarantine, self.exports,
                  self.logs, self.database.parent):
            d.mkdir(parents=True, exist_ok=True)

    # -- paths -----------------------------------------------------------------
    def relative_image_path(self, publisher_slug: str, year: str, sha256: str, ext: str) -> str:
        if not SHA_RE.match(sha256):
            raise StorageError("refusing path for invalid sha256")
        if not EXT_RE.match(ext):
            raise StorageError(f"refusing unsupported extension {ext!r}")
        if not re.match(r"^\d{4}$", year):
            raise StorageError("invalid year")
        slug = slugify(publisher_slug)
        return f"images/{slug}/{year}/{sha256[:2]}/{sha256}.{ext}"

    def resolve(self, rel_path: str) -> Path:
        """Absolute path for a stored relative path; refuses anything escaping the root."""
        if os.path.isabs(rel_path) or "\\" in rel_path:
            raise StorageError(f"refusing absolute/backslash path {rel_path!r}")
        target = (self.root / rel_path).resolve()
        if self.root not in target.parents:
            raise StorageError(f"path escapes data root: {rel_path!r}")
        return target

    def new_temp(self) -> Path:
        self.tmp.mkdir(parents=True, exist_ok=True)
        return self.tmp / f"dl-{secrets.token_hex(8)}.part"

    # -- journal (crash recovery between file move and DB commit) --------------
    def write_journal(self, entry: dict) -> Path:
        self.journal.mkdir(parents=True, exist_ok=True)
        path = self.journal / f"{entry['sha256']}-{secrets.token_hex(4)}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
        return path

    def journal_entries(self) -> list[tuple[Path, dict]]:
        if not self.journal.is_dir():
            return []
        out = []
        for p in sorted(self.journal.glob("*.json")):
            try:
                out.append((p, json.loads(p.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                out.append((p, {}))
        return out

    # -- placing files ---------------------------------------------------------
    def place(self, temp: Path, rel_path: str, sha256: str) -> tuple[Path, bool]:
        """Atomically move a verified temp file to its final path.

        Returns (final_path, already_existed). If a file already exists at the
        content-addressed path and its hash matches, the temp file is discarded
        (same bytes are never stored twice). A mismatching existing file is
        never overwritten.
        """
        final = self.resolve(rel_path)
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            if sha256_file(final) == sha256:
                temp.unlink(missing_ok=True)
                return final, True
            raise StorageError(f"existing file at {rel_path} has a different hash; not overwriting")
        os.replace(temp, final)
        return final, False

    def iter_image_files(self):
        if not self.images.is_dir():
            return
        for p in sorted(self.images.rglob("*")):
            if p.is_file():
                yield p

    def quarantine_file(self, path: Path) -> Path:
        self.quarantine.mkdir(parents=True, exist_ok=True)
        dest = self.quarantine / f"{secrets.token_hex(4)}-{path.name}"
        shutil.move(str(path), dest)
        return dest
