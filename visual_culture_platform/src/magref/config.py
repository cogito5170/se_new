"""Runtime configuration.

Precedence (highest first): explicit CLI flags -> process environment ->
`.env` file (only the file passed with --env-file, or ./.env if it exists) ->
built-in defaults. Every key is documented in `.env.example`.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

IMAGE_MODES = ("off", "header", "colors")


class ConfigError(ValueError):
    """Raised when a configuration value is present but invalid."""


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a minimal KEY=VALUE file. Lines starting with # are ignored.

    No variable expansion, no export keyword handling beyond stripping it.
    """
    values: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            raise ConfigError(f"{path}:{lineno}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = re.split(r"\s+#", value, maxsplit=1)[0].strip()   # inline comment
        values[key.strip()] = value
    return values


def _float(env: dict[str, str], key: str, default: float, minimum: float = 0.0) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc
    if value < minimum:
        raise ConfigError(f"{key} must be >= {minimum}, got {value}")
    return value


def _int(env: dict[str, str], key: str, default: int, minimum: int = 0) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ConfigError(f"{key} must be >= {minimum}, got {value}")
    return value


def _bool(env: dict[str, str], key: str, default: bool) -> bool:
    raw = env.get(key)
    if raw is None or raw == "":
        return default
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{key} must be a boolean (1/0/true/false), got {raw!r}")


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path.home() / "visual_culture_archive"
    db_path: Path | None = None        # default: <data_dir>/database/references.sqlite3
    user_agent: str = "magref/0.1 (+magazine reference research; contact: unset)"
    timeout: float = 15.0              # seconds per request
    request_interval: float = 2.0      # minimum seconds between requests to one host
    max_retries: int = 2               # retries after the first attempt (429/5xx/timeouts)
    backoff_base: float = 1.0          # seconds; doubled per retry
    max_retry_after: float = 60.0      # give up instead of waiting longer than this
    max_concurrency: int = 2           # worker threads for crawl (per-host interval still applies)
    max_page_bytes: int = 5_000_000    # pages/feeds larger than this are rejected
    max_pages_per_run: int = 200       # default cap for discover/crawl
    image_mode: str = "header"         # off | header | colors
    image_header_bytes: int = 65_536   # bytes fetched for header probes
    image_max_bytes: int = 3_000_000   # bytes allowed when image_mode=colors
    images_per_page: int = 3           # how many images per page are probed
    max_file_bytes: int = 20_000_000   # per image file
    max_downloads_per_run: int = 20    # default --limit for download/retry
    max_total_bytes_per_run: int = 200_000_000
    allow_loopback: bool = False       # TEST ONLY: permit 127.0.0.1/::1 (never private ranges)
    respect_robots: bool = True        # not configurable from the environment
    fixture_dir: Path | None = None    # serve all HTTP from local files instead of network
    log_level: str = "INFO"

    def with_overrides(self, **kwargs) -> "Settings":
        clean = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **clean)

    @property
    def database_path(self) -> Path:
        if self.db_path is not None:
            return Path(self.db_path)
        return Path(self.data_dir) / "database" / "references.sqlite3"


def load_settings(env: dict[str, str] | None = None, env_file: Path | None = None) -> Settings:
    merged: dict[str, str] = {}
    if env_file is not None:
        if not env_file.is_file():
            raise ConfigError(f"env file not found: {env_file}")
        merged.update(load_env_file(env_file))
    elif Path(".env").is_file():
        merged.update(load_env_file(Path(".env")))
    merged.update(os.environ if env is None else env)

    image_mode = merged.get("MAGREF_IMAGE_MODE", "header") or "header"
    if image_mode not in IMAGE_MODES:
        raise ConfigError(f"MAGREF_IMAGE_MODE must be one of {IMAGE_MODES}, got {image_mode!r}")
    log_level = (merged.get("MAGREF_LOG_LEVEL") or "INFO").upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        raise ConfigError(f"MAGREF_LOG_LEVEL invalid: {log_level!r}")
    fixture = merged.get("MAGREF_FIXTURE_DIR") or None

    defaults = Settings()
    return Settings(
        # VC_ARCHIVE_DIR is the platform name for the same setting; MAGREF_DATA_DIR wins if both set.
        data_dir=Path(merged.get("MAGREF_DATA_DIR") or merged.get("VC_ARCHIVE_DIR")
                      or defaults.data_dir).expanduser(),
        db_path=Path(merged["MAGREF_DB_PATH"]) if merged.get("MAGREF_DB_PATH") else None,
        user_agent=merged.get("MAGREF_USER_AGENT") or defaults.user_agent,
        timeout=_float(merged, "MAGREF_TIMEOUT", defaults.timeout, 0.1),
        request_interval=_float(merged, "MAGREF_REQUEST_INTERVAL", defaults.request_interval),
        max_retries=_int(merged, "MAGREF_MAX_RETRIES", defaults.max_retries),
        backoff_base=_float(merged, "MAGREF_BACKOFF_BASE", defaults.backoff_base),
        max_retry_after=_float(merged, "MAGREF_MAX_RETRY_AFTER", defaults.max_retry_after),
        max_concurrency=_int(merged, "MAGREF_MAX_CONCURRENCY", defaults.max_concurrency, 1),
        max_page_bytes=_int(merged, "MAGREF_MAX_PAGE_BYTES", defaults.max_page_bytes, 1024),
        max_pages_per_run=_int(merged, "MAGREF_MAX_PAGES_PER_RUN", defaults.max_pages_per_run, 1),
        image_mode=image_mode,
        image_header_bytes=_int(merged, "MAGREF_IMAGE_HEADER_BYTES", defaults.image_header_bytes, 64),
        image_max_bytes=_int(merged, "MAGREF_IMAGE_MAX_BYTES", defaults.image_max_bytes, 1024),
        images_per_page=_int(merged, "MAGREF_IMAGES_PER_PAGE", defaults.images_per_page),
        max_file_bytes=_int(merged, "MAGREF_MAX_FILE_BYTES", defaults.max_file_bytes, 1024),
        max_downloads_per_run=_int(merged, "MAGREF_MAX_DOWNLOADS_PER_RUN",
                                   defaults.max_downloads_per_run, 1),
        max_total_bytes_per_run=_int(merged, "MAGREF_MAX_TOTAL_BYTES_PER_RUN",
                                     defaults.max_total_bytes_per_run, 1024),
        allow_loopback=_bool(merged, "MAGREF_ALLOW_LOOPBACK", False),
        respect_robots=True,
        fixture_dir=Path(fixture) if fixture else None,
        log_level=log_level,
    )
