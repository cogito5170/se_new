"""SQLite schema and migrations.

Strategy: `PRAGMA user_version` holds the applied schema version. `connect()`
applies every migration in MIGRATIONS whose index is above it, each in its own
transaction, so initialization is idempotent and upgrades are forward-only.
The schema is documented in DATA_MODEL.md.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

_POLICY = "('unknown','review_required','allowed','restricted')"
_METHODS = "('sitemap','rss','html','json_catalog')"
_ORIGINS = "('sitemap','rss','html','json_catalog','import')"
_VERIFY = "('verified','partially_supported','hypothesis','unverified','contradicted')"
_CONTEXT_TYPES = ("('social_movement','politics','economy_consumer_culture','technology_tools',"
                  "'popular_culture','subculture','art_movement','design_theory','fashion_ideals',"
                  "'publishing_media','regional_culture','exhibition_event','people_organizations','other')")
_SOURCE_TYPES = ("('journal_article','book','museum_archive','library_archive','official_archive',"
                 "'exhibition_catalogue','dataset','news','website','other')")

MIGRATIONS: list[str] = [
    # ---- v1 ---------------------------------------------------------------
    f"""
    CREATE TABLE sources (
        id                  TEXT PRIMARY KEY,
        name                TEXT NOT NULL,
        base_url            TEXT NOT NULL,
        discovery_method    TEXT NOT NULL CHECK (discovery_method IN {_METHODS}),
        entry_urls          TEXT NOT NULL DEFAULT '[]',
        include_patterns    TEXT NOT NULL DEFAULT '[]',
        exclude_patterns    TEXT NOT NULL DEFAULT '[]',
        allowed_asset_hosts TEXT NOT NULL DEFAULT '[]',
        catalog_mapping     TEXT,
        max_pages           INTEGER CHECK (max_pages IS NULL OR max_pages > 0),
        policy_status       TEXT NOT NULL DEFAULT 'unknown' CHECK (policy_status IN {_POLICY}),
        license             TEXT,
        evidence_url        TEXT,
        terms_url           TEXT,
        policy_note         TEXT,
        policy_reviewed_at  TEXT,
        enabled             INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        last_run_at         TEXT,
        last_run_kind       TEXT,
        last_run_status     TEXT,
        last_error          TEXT
    );

    CREATE TABLE policy_reviews (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        target_kind  TEXT NOT NULL CHECK (target_kind IN ('source', 'image')),
        target_id    TEXT NOT NULL,
        status       TEXT NOT NULL CHECK (status IN {_POLICY}),
        license      TEXT,
        evidence_url TEXT,
        robots_note  TEXT,
        terms_note   TEXT,
        note         TEXT,
        reviewer     TEXT,
        reviewed_at  TEXT NOT NULL
    );
    CREATE INDEX policy_reviews_target ON policy_reviews(target_kind, target_id, id);

    CREATE TABLE discovered_urls (
        url              TEXT PRIMARY KEY,
        source_id        TEXT NOT NULL REFERENCES sources(id),
        discovery_method TEXT NOT NULL CHECK (discovery_method IN {_METHODS}),
        discovered_from  TEXT,
        hints            TEXT NOT NULL DEFAULT '{{}}',
        crawl_status     TEXT NOT NULL DEFAULT 'pending'
                         CHECK (crawl_status IN ('pending','fetched','failed','skipped','blocked')),
        attempts         INTEGER NOT NULL DEFAULT 0,
        last_error       TEXT,
        reference_id     TEXT,
        discovered_at    TEXT NOT NULL,
        updated_at       TEXT NOT NULL
    );
    CREATE INDEX discovered_urls_source ON discovered_urls(source_id, crawl_status);

    CREATE TABLE refs (
        id                TEXT PRIMARY KEY,
        source_id         TEXT NOT NULL REFERENCES sources(id),
        url               TEXT NOT NULL UNIQUE,
        canonical_url     TEXT,
        fetched_url       TEXT,
        discovery_method  TEXT NOT NULL CHECK (discovery_method IN {_ORIGINS}),
        discovered_from   TEXT,
        robots_status     TEXT NOT NULL DEFAULT 'not_checked'
                          CHECK (robots_status IN ('allowed','disallowed','unavailable','not_checked')),
        title             TEXT,
        description       TEXT,
        publisher         TEXT,
        category          TEXT,
        published_at      TEXT,
        modified_at       TEXT,
        language          TEXT,
        page_type         TEXT NOT NULL DEFAULT 'unknown',
        access            TEXT,
        authors           TEXT NOT NULL DEFAULT '[]',
        keywords          TEXT NOT NULL DEFAULT '[]',
        assets            TEXT NOT NULL DEFAULT '[]',
        visual_features   TEXT NOT NULL DEFAULT '{{}}',
        analysis          TEXT NOT NULL DEFAULT '{{}}',
        field_sources     TEXT NOT NULL DEFAULT '{{}}',
        errors            TEXT NOT NULL DEFAULT '[]',
        search_text       TEXT NOT NULL DEFAULT '',
        crawl_status      TEXT NOT NULL DEFAULT 'pending'
                          CHECK (crawl_status IN ('pending','fetched','failed','skipped','blocked')),
        analysis_status   TEXT NOT NULL DEFAULT 'pending'
                          CHECK (analysis_status IN ('pending','partial','complete','failed')),
        http_status       INTEGER,
        content_hash      TEXT,
        extractor_version TEXT,
        first_seen_at     TEXT NOT NULL,
        last_crawled_at   TEXT,
        fetched_at        TEXT,
        updated_at        TEXT NOT NULL
    );
    CREATE UNIQUE INDEX refs_canonical ON refs(canonical_url) WHERE canonical_url IS NOT NULL;
    CREATE INDEX refs_content_hash ON refs(content_hash);
    CREATE INDEX refs_source ON refs(source_id);

    CREATE TABLE ref_urls (
        url          TEXT PRIMARY KEY,
        reference_id TEXT NOT NULL REFERENCES refs(id) ON DELETE CASCADE,
        kind         TEXT NOT NULL CHECK (kind IN ('identity','fetched','canonical','alias')),
        added_at     TEXT NOT NULL
    );

    -- One row per distinct binary (content hash). Many image_refs may point here.
    CREATE TABLE image_files (
        sha256      TEXT PRIMARY KEY CHECK (length(sha256) = 64),
        rel_path    TEXT NOT NULL UNIQUE,
        abs_path    TEXT NOT NULL,
        data_root   TEXT NOT NULL,
        mime_type   TEXT NOT NULL,
        ext         TEXT NOT NULL,
        size_bytes  INTEGER NOT NULL CHECK (size_bytes > 0),
        width       INTEGER,
        height      INTEGER,
        file_status TEXT NOT NULL DEFAULT 'ok'
                    CHECK (file_status IN ('ok','missing','corrupt','relocated')),
        created_at  TEXT NOT NULL,
        verified_at TEXT,
        updated_at  TEXT NOT NULL
    );

    -- One row per normalized image URL (an image reference / candidate).
    CREATE TABLE image_refs (
        id               TEXT PRIMARY KEY,
        url              TEXT NOT NULL UNIQUE,
        source_id        TEXT NOT NULL REFERENCES sources(id),
        source_page_url  TEXT,
        reference_id     TEXT REFERENCES refs(id),
        discovery_method TEXT NOT NULL CHECK (discovery_method IN {_ORIGINS}),
        publisher        TEXT,
        title            TEXT,
        alt              TEXT,
        caption          TEXT,
        description      TEXT,
        creator          TEXT,
        -- Three different dates; never derived from one another.
        publication_date TEXT,     -- when the work was published (magazine issue date, ...)
        creation_date    TEXT,     -- when the work was made
        upload_date      TEXT,     -- when the digital copy was put online (NOT a work date)
        year_start       INTEGER,  -- year range of the WORK (publication/creation), may be uncertain
        year_end         INTEGER,
        year_basis       TEXT CHECK (year_basis IS NULL OR year_basis IN
                                     ('publication','creation','circa','source_declared')),
        country          TEXT,
        region           TEXT,
        media_type       TEXT NOT NULL DEFAULT 'unknown'
                         CHECK (media_type IN ('photograph','illustration','painting','graphic_design',
                                               'typography','print_scan','mixed','unknown')),
        analysis_status  TEXT NOT NULL DEFAULT 'pending'
                         CHECK (analysis_status IN ('pending','measured','failed','not_applicable')),
        review_status    TEXT NOT NULL DEFAULT 'unreviewed'
                         CHECK (review_status IN ('unreviewed','reviewed','needs_attention')),
        declared_width   INTEGER,
        declared_height  INTEGER,
        declared_license TEXT,
        image_type       TEXT NOT NULL DEFAULT 'other'
                         CHECK (image_type IN ('cover','interior_page','editorial_photo',
                                               'portrait','product_photo','other')),
        type_status      TEXT NOT NULL DEFAULT 'unverified'
                         CHECK (type_status IN ('observed','inferred','unverified')),
        type_method      TEXT,
        type_basis       TEXT,
        final_url        TEXT,
        file_sha256      TEXT REFERENCES image_files(sha256),
        download_status  TEXT NOT NULL DEFAULT 'pending'
                         CHECK (download_status IN ('pending','downloaded','failed_transient',
                                                    'failed_permanent','blocked','missing_file')),
        attempt_count    INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
        last_attempt_at  TEXT,
        last_error       TEXT,
        last_error_class TEXT CHECK (last_error_class IS NULL
                                     OR last_error_class IN ('transient','permanent')),
        discovered_at    TEXT NOT NULL,
        updated_at       TEXT NOT NULL,
        CHECK (year_start IS NULL OR year_end IS NULL OR year_start <= year_end)
    );
    CREATE INDEX image_refs_year ON image_refs(year_start, year_end);
    CREATE INDEX image_refs_sha ON image_refs(file_sha256);
    CREATE INDEX image_refs_status ON image_refs(download_status);
    CREATE INDEX image_refs_source ON image_refs(source_id);

    CREATE TABLE download_jobs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        kind        TEXT NOT NULL CHECK (kind IN ('download','retry')),
        started_at  TEXT NOT NULL,
        finished_at TEXT,
        status      TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running','completed','completed_with_errors','failed','stopped_budget')),
        params      TEXT NOT NULL DEFAULT '{{}}',
        stats       TEXT NOT NULL DEFAULT '{{}}'
    );

    CREATE TABLE download_attempts (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id         INTEGER REFERENCES download_jobs(id),
        image_ref_id   TEXT NOT NULL REFERENCES image_refs(id),
        started_at     TEXT NOT NULL,
        finished_at    TEXT NOT NULL,
        outcome        TEXT NOT NULL CHECK (outcome IN ('downloaded','duplicate','failed','blocked')),
        error_class    TEXT CHECK (error_class IS NULL OR error_class IN ('transient','permanent')),
        error_code     TEXT,
        message        TEXT,
        http_status    INTEGER,
        requested_url  TEXT NOT NULL,
        final_url      TEXT,
        bytes_received INTEGER NOT NULL DEFAULT 0,
        sha256         TEXT
    );
    CREATE INDEX download_attempts_ref ON download_attempts(image_ref_id, id);

    CREATE TABLE processing_errors (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id   TEXT,
        target_kind TEXT NOT NULL CHECK (target_kind IN ('source','discovery','page','image','storage')),
        target_id   TEXT,
        url         TEXT,
        stage       TEXT NOT NULL,
        code        TEXT NOT NULL,
        message     TEXT NOT NULL,
        severity    TEXT NOT NULL DEFAULT 'error' CHECK (severity IN ('error','warning')),
        error_class TEXT,
        occurred_at TEXT NOT NULL
    );
    CREATE INDEX processing_errors_time ON processing_errors(occurred_at);

    CREATE TABLE runs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id   TEXT,
        kind        TEXT NOT NULL,
        started_at  TEXT NOT NULL,
        finished_at TEXT,
        status      TEXT NOT NULL DEFAULT 'running',
        stats       TEXT NOT NULL DEFAULT '{{}}'
    );
    """,
    # ---- v2: research platform (genres, features, context, claims, trends, projects) ----
    f"""
    CREATE TABLE genres (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
        parent_id   INTEGER REFERENCES genres(id),
        description TEXT,
        created_at  TEXT NOT NULL
    );
    CREATE TABLE asset_genres (
        asset_id    TEXT NOT NULL REFERENCES image_refs(id) ON DELETE CASCADE,
        genre_id    INTEGER NOT NULL REFERENCES genres(id),
        assigned_by TEXT NOT NULL CHECK (assigned_by IN ('source_declared','human','ai_suggested')),
        created_at  TEXT NOT NULL,
        PRIMARY KEY (asset_id, genre_id)
    );

    -- kind='measured': computed from the stored file bytes (tool + file hash recorded).
    -- kind='semantic': interpretation (style, mood, movement); entered by a human or
    -- suggested by an AI tool, which must be named. Never auto-promoted to reviewed.
    CREATE TABLE visual_features (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id      TEXT NOT NULL REFERENCES image_refs(id) ON DELETE CASCADE,
        feature_type  TEXT NOT NULL,
        feature_value TEXT NOT NULL,
        kind          TEXT NOT NULL CHECK (kind IN ('measured','semantic')),
        method        TEXT NOT NULL,
        tool          TEXT,
        file_sha256   TEXT,
        confidence    REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
        review_status TEXT NOT NULL CHECK (review_status IN
                      ('auto_measured','ai_suggested','human_entered','human_reviewed','rejected')),
        evidence_note TEXT,
        reviewer      TEXT,
        reviewed_at   TEXT,
        created_at    TEXT NOT NULL,
        CHECK (kind <> 'measured' OR (file_sha256 IS NOT NULL AND tool IS NOT NULL)),
        CHECK (review_status <> 'ai_suggested' OR tool IS NOT NULL),
        CHECK (kind <> 'measured' OR review_status IN ('auto_measured','rejected'))
    );
    CREATE INDEX visual_features_asset ON visual_features(asset_id, feature_type);
    CREATE INDEX visual_features_value ON visual_features(feature_type, feature_value);

    CREATE TABLE context_records (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        title               TEXT NOT NULL,
        description         TEXT NOT NULL,
        context_type        TEXT NOT NULL CHECK (context_type IN {_CONTEXT_TYPES}),
        start_year          INTEGER,
        end_year            INTEGER,
        period_precision    TEXT NOT NULL DEFAULT 'unknown'
                            CHECK (period_precision IN ('exact','approximate','unknown')),
        country             TEXT,
        region              TEXT,
        related_people      TEXT NOT NULL DEFAULT '[]',
        verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN {_VERIFY}),
        alternative_interpretations TEXT,
        last_reviewed_at    TEXT,
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL,
        CHECK (start_year IS NULL OR end_year IS NULL OR start_year <= end_year)
    );
    CREATE TABLE context_genres (
        context_id INTEGER NOT NULL REFERENCES context_records(id) ON DELETE CASCADE,
        genre_id   INTEGER NOT NULL REFERENCES genres(id),
        PRIMARY KEY (context_id, genre_id)
    );

    CREATE TABLE research_sources (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        title            TEXT NOT NULL,
        source_type      TEXT NOT NULL CHECK (source_type IN {_SOURCE_TYPES}),
        author           TEXT,
        publisher        TEXT,
        publication_date TEXT,
        url              TEXT,
        identifier       TEXT,
        accessed_at      TEXT,
        notes            TEXT,
        created_at       TEXT NOT NULL
    );
    CREATE TABLE context_sources (
        context_id INTEGER NOT NULL REFERENCES context_records(id) ON DELETE CASCADE,
        source_id  INTEGER NOT NULL REFERENCES research_sources(id),
        note       TEXT,
        PRIMARY KEY (context_id, source_id)
    );

    CREATE TABLE research_claims (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        claim_text               TEXT NOT NULL,
        claim_type               TEXT NOT NULL CHECK (claim_type IN
                                 ('historical_fact','interpretation','influence','trend','attribution','other')),
        context_id               INTEGER REFERENCES context_records(id),
        verification_status      TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN {_VERIFY}),
        confidence               REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
        alternative_explanations TEXT,
        reviewer                 TEXT,
        reviewed_at              TEXT,
        created_at               TEXT NOT NULL,
        updated_at               TEXT NOT NULL
    );
    -- How a source relates to a claim, and how much of the source was actually read.
    CREATE TABLE claim_sources (
        claim_id     INTEGER NOT NULL REFERENCES research_claims(id) ON DELETE CASCADE,
        source_id    INTEGER NOT NULL REFERENCES research_sources(id),
        relation     TEXT NOT NULL CHECK (relation IN ('supports','partially_supports','contradicts','mentions')),
        access_level TEXT NOT NULL CHECK (access_level IN ('title_only','abstract','excerpt','full_text')),
        locator      TEXT,
        quote        TEXT,
        note         TEXT,
        created_at   TEXT NOT NULL,
        PRIMARY KEY (claim_id, source_id)
    );
    -- Backstop for the rule enforced in research.ClaimRepo: 'verified' needs a supporting
    -- source that was read beyond its title/abstract.
    CREATE TRIGGER claims_verified_need_evidence
    BEFORE UPDATE OF verification_status ON research_claims
    WHEN NEW.verification_status = 'verified' AND NOT EXISTS (
        SELECT 1 FROM claim_sources WHERE claim_id = NEW.id AND relation = 'supports'
        AND access_level IN ('excerpt','full_text'))
    BEGIN SELECT RAISE(ABORT, 'verified claim needs a supporting source read beyond title/abstract'); END;
    CREATE TRIGGER claims_insert_unverified
    BEFORE INSERT ON research_claims WHEN NEW.verification_status <> 'unverified'
    BEGIN SELECT RAISE(ABORT, 'claims start unverified; set status through review'); END;

    CREATE TABLE asset_context (
        asset_id        TEXT NOT NULL REFERENCES image_refs(id) ON DELETE CASCADE,
        context_id      INTEGER NOT NULL REFERENCES context_records(id) ON DELETE CASCADE,
        relation_type   TEXT NOT NULL CHECK (relation_type IN ('same_period','visual_similarity',
                        'documented_influence','thematic_relation','research_hypothesis')),
        explanation     TEXT,
        evidence_status TEXT NOT NULL DEFAULT 'unverified' CHECK (evidence_status IN {_VERIFY}),
        claim_id        INTEGER REFERENCES research_claims(id),
        created_at      TEXT NOT NULL,
        PRIMARY KEY (asset_id, context_id, relation_type)
    );
    CREATE TRIGGER documented_influence_needs_verified_claim
    BEFORE INSERT ON asset_context WHEN NEW.relation_type = 'documented_influence' AND (
        NEW.claim_id IS NULL OR
        (SELECT verification_status FROM research_claims WHERE id = NEW.claim_id) <> 'verified')
    BEGIN SELECT RAISE(ABORT, 'documented_influence requires a verified claim'); END;

    CREATE TABLE trend_observations (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        title               TEXT NOT NULL,
        genre_id            INTEGER REFERENCES genres(id),
        start_year          INTEGER,
        end_year            INTEGER,
        region              TEXT,
        feature_definition  TEXT NOT NULL,
        sample_size         INTEGER NOT NULL CHECK (sample_size >= 0),
        observed_result     TEXT NOT NULL,
        method              TEXT NOT NULL,
        limitations         TEXT NOT NULL,
        source_asset_ids    TEXT NOT NULL DEFAULT '[]',
        verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN {_VERIFY}),
        created_at          TEXT NOT NULL
    );

    CREATE TABLE design_projects (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        title             TEXT NOT NULL,
        brief             TEXT,
        target_audience   TEXT,
        medium            TEXT,
        constraints       TEXT,
        reference_genres  TEXT NOT NULL DEFAULT '[]',
        reference_periods TEXT NOT NULL DEFAULT '[]',
        reference_regions TEXT NOT NULL DEFAULT '[]',
        direction_notes   TEXT,
        excluded_styles   TEXT,
        final_review      TEXT,
        created_at        TEXT NOT NULL,
        updated_at        TEXT NOT NULL
    );
    CREATE TABLE project_assets (
        project_id INTEGER NOT NULL REFERENCES design_projects(id) ON DELETE CASCADE,
        asset_id   TEXT NOT NULL REFERENCES image_refs(id),
        group_name TEXT NOT NULL DEFAULT 'default',
        note       TEXT,
        added_at   TEXT NOT NULL,
        PRIMARY KEY (project_id, asset_id)
    );
    CREATE TABLE project_contexts (
        project_id INTEGER NOT NULL REFERENCES design_projects(id) ON DELETE CASCADE,
        context_id INTEGER NOT NULL REFERENCES context_records(id),
        note       TEXT,
        added_at   TEXT NOT NULL,
        PRIMARY KEY (project_id, context_id)
    );
    CREATE TABLE project_features (
        project_id    INTEGER NOT NULL REFERENCES design_projects(id) ON DELETE CASCADE,
        feature_type  TEXT NOT NULL,
        feature_value TEXT NOT NULL,
        note          TEXT,
        PRIMARY KEY (project_id, feature_type, feature_value)
    );
    CREATE TABLE project_notes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL REFERENCES design_projects(id) ON DELETE CASCADE,
        body       TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE project_reports (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id   INTEGER NOT NULL REFERENCES design_projects(id) ON DELETE CASCADE,
        format       TEXT NOT NULL CHECK (format IN ('markdown','json','html')),
        content      TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        reviewed     INTEGER NOT NULL DEFAULT 0 CHECK (reviewed IN (0, 1))
    );
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    migrate(conn)
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def migrate(conn: sqlite3.Connection) -> int:
    version = current_version(conn)
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"database schema v{version} is newer than this program (v{SCHEMA_VERSION})")
    for index in range(version, SCHEMA_VERSION):
        script = MIGRATIONS[index]
        # executescript() commits first; wrap explicitly so a failed migration leaves nothing.
        try:
            conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {index + 1};\nCOMMIT;")
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    return current_version(conn)
