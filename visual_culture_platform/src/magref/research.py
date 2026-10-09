"""Genres, visual features, research sources, claims, context records and relations.

Trust rules enforced here (and, where possible, by SQLite triggers as a backstop):

* Claims and context records are created `unverified`. Nothing promotes them
  automatically -- every status change is an explicit review naming a reviewer.
* `verified` needs a supporting source that was read beyond its title/abstract
  (access_level excerpt or full_text) and no contradicting source read at
  that level. Finding that a source EXISTS is not evidence that it SUPPORTS
  the claim; the relation and access level are recorded per claim-source link.
* `documented_influence` between an asset and a context needs a verified claim.
* `same_period` is checked against the asset's and context's year ranges and is
  never a causal statement.
* Measured visual features are computed from stored bytes (tool + file hash
  recorded). Semantic features (style, mood, movement...) are interpretations:
  `human_entered` or `ai_suggested` (tool/model must be named), and only a
  human review turns them into `human_reviewed`.
"""
from __future__ import annotations

import json
import sqlite3

from .timeutil import normalize_date, utcnow
from .urls import InvalidURL, normalize_url

VERIFICATION_STATUSES = ("verified", "partially_supported", "hypothesis", "unverified", "contradicted")
CONTEXT_TYPES = ("social_movement", "politics", "economy_consumer_culture", "technology_tools",
                 "popular_culture", "subculture", "art_movement", "design_theory", "fashion_ideals",
                 "publishing_media", "regional_culture", "exhibition_event", "people_organizations",
                 "other")
SOURCE_TYPES = ("journal_article", "book", "museum_archive", "library_archive", "official_archive",
                "exhibition_catalogue", "dataset", "news", "website", "other")
CLAIM_TYPES = ("historical_fact", "interpretation", "influence", "trend", "attribution", "other")
RELATIONS = ("supports", "partially_supports", "contradicts", "mentions")
ACCESS_LEVELS = ("title_only", "abstract", "excerpt", "full_text")
READ_LEVELS = ("excerpt", "full_text")
ASSET_CONTEXT_RELATIONS = ("same_period", "visual_similarity", "documented_influence",
                           "thematic_relation", "research_hypothesis")
MEASURED_FEATURES = ("width", "height", "aspect_ratio", "orientation", "file_size", "palette",
                     "dominant_color", "dominant_hue", "brightness_mean", "brightness_level",
                     "contrast_rms", "contrast_level", "saturation_mean", "colorfulness",
                     "colorfulness_level")
SEMANTIC_FEATURES = ("style", "art_movement", "mood", "composition", "layout_type", "typography",
                     "whitespace_density", "information_density", "medium", "lighting", "texture",
                     "form_rhythm", "styling", "motif", "color_contrast", "cultural_reading")


class RuleError(ValueError):
    """A trust rule refused the change. The message says which evidence is missing."""


def _now() -> str:
    return utcnow()


def _check_years(start, end) -> None:
    if start is not None and end is not None and int(start) > int(end):
        raise RuleError("start_year must be <= end_year")


# --------------------------------------------------------------------------- genres

class GenreRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def ensure(self, path: str, description: str | None = None) -> int:
        """'graphic design/poster' creates both levels; returns the leaf id."""
        parent = None
        gid = None
        parts = [p.strip() for p in path.split("/") if p.strip()]
        if not parts:
            raise RuleError("empty genre name")
        for i, name in enumerate(parts):
            row = self.conn.execute("SELECT id, parent_id FROM genres WHERE name=? COLLATE NOCASE",
                                    (name,)).fetchone()
            if row is None:
                with self.conn:
                    cur = self.conn.execute(
                        "INSERT INTO genres (name, parent_id, description, created_at) VALUES (?,?,?,?)",
                        (name, parent, description if i == len(parts) - 1 else None, _now()))
                gid = cur.lastrowid
            else:
                gid = row[0]
            parent = gid
        return gid

    def get(self, name_or_id) -> dict | None:
        if isinstance(name_or_id, int) or str(name_or_id).isdigit():
            row = self.conn.execute("SELECT * FROM genres WHERE id=?", (int(name_or_id),)).fetchone()
        else:
            row = self.conn.execute("SELECT * FROM genres WHERE name=? COLLATE NOCASE",
                                    (str(name_or_id).split("/")[-1].strip(),)).fetchone()
        return dict(row) if row else None

    def all(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            """SELECT g.*, (SELECT COUNT(*) FROM asset_genres a WHERE a.genre_id=g.id) AS asset_count
               FROM genres g ORDER BY g.name""")]

    def with_descendants(self, name_or_id) -> list[int]:
        g = self.get(name_or_id)
        if g is None:
            return []
        ids, frontier = [g["id"]], [g["id"]]
        while frontier:
            rows = self.conn.execute(
                f"SELECT id FROM genres WHERE parent_id IN ({', '.join('?' * len(frontier))})",
                frontier).fetchall()
            frontier = [r[0] for r in rows if r[0] not in ids]
            ids.extend(frontier)
        return ids

    def link_asset(self, asset_id: str, genre_id: int, assigned_by: str = "human") -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO asset_genres (asset_id, genre_id, assigned_by, created_at) "
                "VALUES (?,?,?,?)", (asset_id, genre_id, assigned_by, _now()))

    def unlink_asset(self, asset_id: str, genre_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM asset_genres WHERE asset_id=? AND genre_id=?",
                              (asset_id, genre_id))


# --------------------------------------------------------------------------- features

class FeatureRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add_measured(self, asset_id: str, feature_type: str, value, *, method: str, tool: str,
                     file_sha256: str, note: str | None = None) -> int:
        if feature_type not in MEASURED_FEATURES:
            raise RuleError(f"unknown measured feature {feature_type!r}")
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO visual_features (asset_id, feature_type, feature_value, kind, method,
                   tool, file_sha256, confidence, review_status, evidence_note, created_at)
                   VALUES (?,?,?,'measured',?,?,?,NULL,'auto_measured',?,?)""",
                (asset_id, feature_type, _value(value), method, tool, file_sha256, note, _now()))
        return cur.lastrowid

    def add_semantic(self, asset_id: str, feature_type: str, value: str, *, origin: str,
                     method: str, tool: str | None = None, confidence: float | None = None,
                     evidence_note: str | None = None, reviewer: str | None = None) -> int:
        if feature_type not in SEMANTIC_FEATURES:
            raise RuleError(f"unknown semantic feature {feature_type!r}; one of {SEMANTIC_FEATURES}")
        if origin == "ai":
            if not tool:
                raise RuleError("AI-suggested features must name the model/tool")
            status = "ai_suggested"
        elif origin == "human":
            status = "human_entered"
        else:
            raise RuleError("origin must be 'human' or 'ai'")
        if confidence is not None and not 0 <= confidence <= 1:
            raise RuleError("confidence must be between 0 and 1")
        if self.conn.execute("SELECT 1 FROM image_refs WHERE id=?", (asset_id,)).fetchone() is None:
            raise RuleError(f"asset {asset_id} not found")
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO visual_features (asset_id, feature_type, feature_value, kind, method,
                   tool, confidence, review_status, evidence_note, reviewer, created_at)
                   VALUES (?,?,?,'semantic',?,?,?,?,?,?,?)""",
                (asset_id, feature_type, str(value).strip(), method, tool, confidence, status,
                 evidence_note, reviewer if origin == "human" else None, _now()))
        return cur.lastrowid

    def review(self, feature_id: int, decision: str, reviewer: str, note: str | None = None) -> dict:
        if not reviewer:
            raise RuleError("a review needs a reviewer name")
        row = self.conn.execute("SELECT * FROM visual_features WHERE id=?", (feature_id,)).fetchone()
        if row is None:
            raise RuleError(f"feature {feature_id} not found")
        if decision == "accept":
            if row["kind"] == "measured":
                raise RuleError("measured values are not 'accepted'; they are recomputed or rejected")
            status = "human_reviewed"
        elif decision == "reject":
            status = "rejected"
        else:
            raise RuleError("decision must be 'accept' or 'reject'")
        note_text = row["evidence_note"] or ""
        if note:
            note_text = (note_text + "\n" if note_text else "") + f"review: {note}"
        with self.conn:
            self.conn.execute("UPDATE visual_features SET review_status=?, reviewer=?, reviewed_at=?, "
                              "evidence_note=? WHERE id=?",
                              (status, reviewer, _now(), note_text or None, feature_id))
        return dict(self.conn.execute("SELECT * FROM visual_features WHERE id=?", (feature_id,)).fetchone())

    def for_asset(self, asset_id: str, include_rejected: bool = False) -> list[dict]:
        sql = "SELECT * FROM visual_features WHERE asset_id=?"
        if not include_rejected:
            sql += " AND review_status <> 'rejected'"
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY kind, feature_type, id", (asset_id,))]

    def clear_measured(self, asset_id: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM visual_features WHERE asset_id=? AND kind='measured'",
                              (asset_id,))


def _value(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------------- sources & claims

class ResearchSourceRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, title: str, source_type: str, *, author=None, publisher=None,
            publication_date=None, url=None, identifier=None, accessed_at=None, notes=None) -> int:
        if not title or not title.strip():
            raise RuleError("source title is required")
        if source_type not in SOURCE_TYPES:
            raise RuleError(f"source_type must be one of {SOURCE_TYPES}")
        if url:
            try:
                url = normalize_url(url)
            except InvalidURL as exc:
                raise RuleError(f"invalid URL: {exc}") from exc
        if publication_date:
            norm = normalize_date(publication_date)
            if norm is None and not str(publication_date).strip().isdigit():
                raise RuleError(f"publication_date {publication_date!r} is not a date or year")
            publication_date = norm or str(publication_date).strip()
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO research_sources (title, source_type, author, publisher, publication_date,
                   url, identifier, accessed_at, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (title.strip(), source_type, author, publisher, publication_date, url, identifier,
                 accessed_at, notes, _now()))
        return cur.lastrowid

    def get(self, source_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM research_sources WHERE id=?", (source_id,)).fetchone()
        return dict(row) if row else None

    def all(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM research_sources ORDER BY id")]


class ClaimRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, claim_text: str, claim_type: str, *, context_id: int | None = None,
            alternative_explanations: str | None = None) -> int:
        if not claim_text or not claim_text.strip():
            raise RuleError("claim text is required")
        if claim_type not in CLAIM_TYPES:
            raise RuleError(f"claim_type must be one of {CLAIM_TYPES}")
        now = _now()
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO research_claims (claim_text, claim_type, context_id,
                   alternative_explanations, created_at, updated_at) VALUES (?,?,?,?,?,?)""",
                (claim_text.strip(), claim_type, context_id, alternative_explanations, now, now))
        return cur.lastrowid

    def get(self, claim_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM research_claims WHERE id=?", (claim_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["evidence"] = self.evidence(claim_id)
        return d

    def evidence(self, claim_id: int) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            """SELECT cs.*, s.title, s.source_type, s.url, s.author, s.publisher, s.publication_date
               FROM claim_sources cs JOIN research_sources s ON s.id = cs.source_id
               WHERE cs.claim_id=? ORDER BY s.id""", (claim_id,))]

    def link_source(self, claim_id: int, source_id: int, relation: str, access_level: str, *,
                    locator: str | None = None, quote: str | None = None, note: str | None = None) -> None:
        if relation not in RELATIONS:
            raise RuleError(f"relation must be one of {RELATIONS}")
        if access_level not in ACCESS_LEVELS:
            raise RuleError(f"access_level must be one of {ACCESS_LEVELS}")
        if relation in ("supports", "partially_supports", "contradicts") and access_level == "title_only":
            raise RuleError("a source known only by its title cannot support or contradict a claim; "
                            "use relation 'mentions' until it has been read")
        if self.get(claim_id) is None:
            raise RuleError(f"claim {claim_id} not found")
        if self.conn.execute("SELECT 1 FROM research_sources WHERE id=?", (source_id,)).fetchone() is None:
            raise RuleError(f"research source {source_id} not found")
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO claim_sources (claim_id, source_id, relation, access_level,
                   locator, quote, note, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (claim_id, source_id, relation, access_level, locator, quote, note, _now()))

    def allowed_statuses(self, claim_id: int) -> dict[str, str | None]:
        """status -> None if allowed, else the reason it is refused."""
        ev = self.evidence(claim_id)
        read_support = [e for e in ev if e["relation"] == "supports" and e["access_level"] in READ_LEVELS]
        any_support = [e for e in ev if e["relation"] in ("supports", "partially_supports")
                       and e["access_level"] != "title_only"]
        read_contra = [e for e in ev if e["relation"] == "contradicts" and e["access_level"] != "title_only"]
        out: dict[str, str | None] = {"unverified": None, "hypothesis": None}
        if not read_support:
            out["verified"] = ("needs a source with relation 'supports' read at excerpt or full_text "
                               "level (title or abstract alone is not verification)")
        elif read_contra:
            out["verified"] = ("a read source contradicts this claim; use 'partially_supported' or "
                               "'contradicted' and record the alternative explanation")
        else:
            out["verified"] = None
        out["partially_supported"] = None if any_support else \
            "needs at least one supporting/partially supporting source read beyond its title"
        out["contradicted"] = None if read_contra else "needs a contradicting source read beyond its title"
        return out

    def set_status(self, claim_id: int, status: str, *, reviewer: str,
                   confidence: float | None = None, alternative_explanations: str | None = None) -> dict:
        if status not in VERIFICATION_STATUSES:
            raise RuleError(f"status must be one of {VERIFICATION_STATUSES}")
        if not reviewer or not reviewer.strip():
            raise RuleError("status changes need a reviewer (statuses are never set automatically)")
        if self.get(claim_id) is None:
            raise RuleError(f"claim {claim_id} not found")
        reason = self.allowed_statuses(claim_id).get(status)
        if reason:
            raise RuleError(f"cannot set '{status}': {reason}")
        if confidence is not None and not 0 <= confidence <= 1:
            raise RuleError("confidence must be between 0 and 1")
        sets = ["verification_status=?", "reviewer=?", "reviewed_at=?", "updated_at=?", "confidence=?"]
        args = [status, reviewer.strip(), _now(), _now(), confidence]
        if alternative_explanations is not None:
            sets.append("alternative_explanations=?")
            args.append(alternative_explanations)
        with self.conn:
            self.conn.execute(f"UPDATE research_claims SET {', '.join(sets)} WHERE id=?", args + [claim_id])
        return self.get(claim_id)

    def pending_review(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            """SELECT * FROM research_claims WHERE verification_status IN ('unverified','hypothesis')
               ORDER BY id""")]


# --------------------------------------------------------------------------- contexts

class ContextRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, title: str, description: str, context_type: str, *, start_year=None,
            end_year=None, period_precision: str = "unknown", country=None, region=None,
            related_people: list[str] | None = None, alternative_interpretations=None,
            genres: list[str] | None = None) -> int:
        if not title or not description:
            raise RuleError("title and description are required")
        if context_type not in CONTEXT_TYPES:
            raise RuleError(f"context_type must be one of {CONTEXT_TYPES}")
        _check_years(start_year, end_year)
        if period_precision not in ("exact", "approximate", "unknown"):
            raise RuleError("period_precision must be exact|approximate|unknown")
        if start_year is None and end_year is None:
            period_precision = "unknown"
        now = _now()
        with self.conn:
            cur = self.conn.execute(
                """INSERT INTO context_records (title, description, context_type, start_year, end_year,
                   period_precision, country, region, related_people, alternative_interpretations,
                   created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (title, description, context_type, start_year, end_year, period_precision, country,
                 region, json.dumps(related_people or [], ensure_ascii=False),
                 alternative_interpretations, now, now))
        cid = cur.lastrowid
        for g in genres or []:
            gid = GenreRepo(self.conn).ensure(g)
            with self.conn:
                self.conn.execute("INSERT OR IGNORE INTO context_genres VALUES (?,?)", (cid, gid))
        return cid

    def get(self, context_id: int) -> dict | None:
        row = self.conn.execute("SELECT * FROM context_records WHERE id=?", (context_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["related_people"] = json.loads(d["related_people"])
        d["genres"] = [r[0] for r in self.conn.execute(
            "SELECT g.name FROM context_genres c JOIN genres g ON g.id=c.genre_id WHERE c.context_id=?",
            (context_id,))]
        d["claims"] = [ClaimRepo(self.conn).get(r[0]) for r in self.conn.execute(
            "SELECT id FROM research_claims WHERE context_id=? ORDER BY id", (context_id,))]
        d["sources"] = [dict(r) for r in self.conn.execute(
            """SELECT s.*, cs.note AS link_note FROM context_sources cs
               JOIN research_sources s ON s.id=cs.source_id WHERE cs.context_id=?""", (context_id,))]
        d["assets"] = [dict(r) for r in self.conn.execute(
            "SELECT * FROM asset_context WHERE context_id=? ORDER BY asset_id", (context_id,))]
        return d

    def search(self, text: str | None = None, *, year_from=None, year_to=None, country=None,
               context_type=None, status=None) -> list[dict]:
        sql, args = ["SELECT * FROM context_records WHERE 1=1"], []
        if text:
            sql.append("AND (lower(title) LIKE ? OR lower(description) LIKE ?)")
            args += [f"%{text.lower()}%"] * 2
        if year_to is not None:
            sql.append("AND (start_year IS NULL OR start_year <= ?)")
            args.append(year_to)
        if year_from is not None:
            sql.append("AND (end_year IS NULL OR end_year >= ?)")
            args.append(year_from)
        if country:
            sql.append("AND lower(country)=lower(?)")
            args.append(country)
        if context_type:
            sql.append("AND context_type=?")
            args.append(context_type)
        if status:
            sql.append("AND verification_status=?")
            args.append(status)
        sql.append("ORDER BY start_year IS NULL, start_year, id")
        return [dict(r) for r in self.conn.execute(" ".join(sql), args)]

    def link_source(self, context_id: int, source_id: int, note: str | None = None) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO context_sources VALUES (?,?,?)",
                              (context_id, source_id, note))

    def set_status(self, context_id: int, status: str, *, reviewer: str) -> dict:
        """A context's status follows its claims: it cannot be stronger than its best claim."""
        if status not in VERIFICATION_STATUSES:
            raise RuleError(f"status must be one of {VERIFICATION_STATUSES}")
        if not reviewer:
            raise RuleError("status changes need a reviewer")
        ctx = self.get(context_id)
        if ctx is None:
            raise RuleError(f"context {context_id} not found")
        claim_status = {c["verification_status"] for c in ctx["claims"]}
        if status == "verified" and "verified" not in claim_status:
            raise RuleError("cannot set 'verified': no verified claim is attached to this context")
        if status == "partially_supported" and not claim_status & {"verified", "partially_supported"}:
            raise RuleError("cannot set 'partially_supported': no supported claim is attached")
        if status == "contradicted" and "contradicted" not in claim_status:
            raise RuleError("cannot set 'contradicted': no contradicted claim is attached")
        with self.conn:
            self.conn.execute("UPDATE context_records SET verification_status=?, last_reviewed_at=?, "
                              "updated_at=? WHERE id=?", (status, _now(), _now(), context_id))
        return self.get(context_id)

    def relate_asset(self, asset_id: str, context_id: int, relation_type: str, *,
                     explanation: str | None = None, claim_id: int | None = None) -> dict:
        if relation_type not in ASSET_CONTEXT_RELATIONS:
            raise RuleError(f"relation_type must be one of {ASSET_CONTEXT_RELATIONS}")
        asset = self.conn.execute("SELECT year_start, year_end FROM image_refs WHERE id=?",
                                  (asset_id,)).fetchone()
        if asset is None:
            raise RuleError(f"asset {asset_id} not found")
        ctx = self.get(context_id)
        if ctx is None:
            raise RuleError(f"context {context_id} not found")
        claim = ClaimRepo(self.conn).get(claim_id) if claim_id is not None else None
        if claim_id is not None and claim is None:
            raise RuleError(f"claim {claim_id} not found")
        if relation_type == "documented_influence" and (claim is None or claim["verification_status"] != "verified"):
            raise RuleError("documented_influence needs a verified claim with sources; "
                            "record it as 'research_hypothesis' until then")
        if relation_type == "same_period":
            if asset["year_start"] is None:
                raise RuleError("asset has no known year; same_period cannot be asserted")
            if ctx["start_year"] is None and ctx["end_year"] is None:
                raise RuleError("context has no period; same_period cannot be asserted")
            cs = ctx["start_year"] if ctx["start_year"] is not None else -10**6
            ce = ctx["end_year"] if ctx["end_year"] is not None else 10**6
            if asset["year_start"] > ce or asset["year_end"] < cs:
                raise RuleError("asset years do not overlap the context period")
            note = "Temporal overlap only; this does not imply influence or causation."
            explanation = f"{explanation} -- {note}" if explanation else note
        if claim is not None:
            evidence = claim["verification_status"]
        elif relation_type == "research_hypothesis":
            evidence = "hypothesis"
        else:
            evidence = "unverified"
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO asset_context (asset_id, context_id, relation_type, explanation,
                   evidence_status, claim_id, created_at) VALUES (?,?,?,?,?,?,?)""",
                (asset_id, context_id, relation_type, explanation, evidence, claim_id, _now()))
        return dict(self.conn.execute(
            "SELECT * FROM asset_context WHERE asset_id=? AND context_id=? AND relation_type=?",
            (asset_id, context_id, relation_type)).fetchone())

    def for_asset(self, asset_id: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            """SELECT ac.*, c.title, c.verification_status AS context_status, c.start_year, c.end_year
               FROM asset_context ac JOIN context_records c ON c.id = ac.context_id
               WHERE ac.asset_id=? ORDER BY c.start_year, c.id""", (asset_id,))]
