from pathlib import Path

from helpers import ROOT, raises

from magref.config import ConfigError, load_settings


def test_env_example_parses_with_inline_comments():
    s = load_settings(env={}, env_file=ROOT / ".env.example")
    assert s.request_interval == 2.0 and s.image_mode == "header" and s.allow_loopback is False
    assert s.data_dir == Path.home() / "visual_culture_archive"
    assert s.database_path == s.data_dir / "database" / "references.sqlite3"


def test_precedence_and_aliases(tmp_path):
    s = load_settings(env={"VC_ARCHIVE_DIR": str(tmp_path / "vc")}, env_file=ROOT / ".env.example")
    assert s.data_dir == tmp_path / "vc"
    s = load_settings(env={"VC_ARCHIVE_DIR": "/a", "MAGREF_DATA_DIR": str(tmp_path / "m")},
                      env_file=ROOT / ".env.example")
    assert s.data_dir == tmp_path / "m"


def test_invalid_values_are_rejected(tmp_path):
    for env in ({"MAGREF_TIMEOUT": "fast"}, {"MAGREF_MAX_RETRIES": "-1"}, {"MAGREF_IMAGE_MODE": "full"},
                {"MAGREF_ALLOW_LOOPBACK": "maybe"}, {"MAGREF_MAX_CONCURRENCY": "0"}):
        raises(ConfigError, load_settings, env, None)
    raises(ConfigError, load_settings, {}, tmp_path / "missing.env")
