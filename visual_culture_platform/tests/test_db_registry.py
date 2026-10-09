import sqlite3

from helpers import make_app, raises

from magref import db
from magref.registry import Registry, RegistryError, Source


def test_schema_initialization_is_idempotent(tmp_path):
    path = tmp_path / "x.sqlite3"
    c1 = db.connect(path)
    assert db.current_version(c1) == db.SCHEMA_VERSION
    c1.close()
    c2 = db.connect(path)                                    # second open: no error, same version
    assert db.current_version(c2) == db.SCHEMA_VERSION
    tables = {r[0] for r in c2.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("sources", "image_refs", "image_files", "download_jobs", "download_attempts",
              "policy_reviews", "processing_errors", "genres", "asset_genres", "visual_features",
              "context_records", "research_sources", "research_claims", "claim_sources",
              "asset_context", "trend_observations", "design_projects", "project_assets"):
        assert t in tables, t


def test_constraints_reject_bad_rows(tmp_path):
    app = make_app(tmp_path)
    c = app.conn
    raises(sqlite3.IntegrityError, c.execute,
           "INSERT INTO sources (id,name,base_url,discovery_method,created_at,updated_at) VALUES ('a','a','x','ftp','t','t')")
    Registry(c).add(Source(id="s", name="s", base_url="https://m.test/", discovery_method="html"))
    raises(sqlite3.IntegrityError, c.execute,
           "INSERT INTO image_refs (id,url,source_id,discovery_method,discovered_at,updated_at,download_status) "
           "VALUES ('mi_x','https://m.test/a','s','html','t','t','done')")
    raises(sqlite3.IntegrityError, c.execute,
           "INSERT INTO image_refs (id,url,source_id,discovery_method,discovered_at,updated_at,year_start,year_end) "
           "VALUES ('mi_y','https://m.test/b','s','html','t','t',2000,1990)")
    raises(sqlite3.IntegrityError, c.execute,
           "INSERT INTO image_files (sha256,rel_path,abs_path,data_root,mime_type,ext,size_bytes,created_at,updated_at)"
           " VALUES ('short','r','a','d','image/png','png',1,'t','t')")


def test_source_validation_and_policy_reviews(tmp_path):
    reg = Registry(make_app(tmp_path).conn)
    raises(RegistryError, reg.add, Source(id="Bad ID", name="x", base_url="https://m.test/", discovery_method="html"))
    raises(RegistryError, reg.add, Source(id="x", name="x", base_url="ftp://m.test/", discovery_method="html"))
    raises(RegistryError, reg.add, Source(id="x", name="x", base_url="https://m.test/", discovery_method="html",
                                          policy_status="allowed"))          # no evidence
    raises(RegistryError, reg.add, Source(id="x", name="x", base_url="https://m.test/", discovery_method="json_catalog"))
    s = reg.add(Source(id="x", name="x", base_url="HTTPS://M.test", discovery_method="html"))
    assert s.base_url == "https://m.test/" and s.policy_status == "unknown" and s.enabled
    raises(RegistryError, reg.add, Source(id="x", name="dup", base_url="https://m.test/", discovery_method="html"))
    reg.review_source("x", "review_required", note="terms unclear", reviewer="alice")
    reg.review_source("x", "allowed", license="CC-BY-4.0", evidence_url="https://m.test/terms", reviewer="alice")
    hist = reg.review_history("source", "x")
    assert [h["status"] for h in hist] == ["review_required", "allowed"] and hist[1]["reviewer"] == "alice"
    assert reg.get("x").policy_status == "allowed"
    assert reg.set_enabled("x", False).enabled is False
