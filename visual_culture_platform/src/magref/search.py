"""Deterministic keyword search with filters. NOT semantic or vector search.

`SearchBackend` is the interface; `KeywordSearch` is the only implementation.
A future embedding backend can implement the same `search(SearchQuery)`.

Ranking: for every query term and every field containing it,
    score += field_weight * (1 + ln(term frequency in field))
then multiplied by coverage = matched_terms / query_terms. Ties break on ID,
so identical input always gives identical order. Each hit explains which
terms matched in which fields, and which matched only inferred labels.
Tokens: lower-cased \\w+ runs (works for Hangul), a small English stop list,
and light suffix stripping (plural -s/-es/-ies, -ism/-ist) -- nothing more.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Protocol

STOPWORDS = {"a", "an", "and", "the", "of", "for", "with", "in", "on", "to", "or", "by", "at",
             "find", "references", "reference", "show", "me", "that", "use", "using", "from"}

PAGE_FIELDS = {"title": 3.0, "keywords": 2.5, "description": 2.0, "category": 1.5,
               "inferred_labels": 1.5, "image_text": 1.0, "publisher": 1.0}
IMAGE_FIELDS = {"title": 3.0, "alt": 2.5, "caption": 2.0, "description": 2.0, "genres": 2.0,
                "semantic_features": 1.5, "image_type": 1.5, "creator": 1.5, "page_title": 1.0,
                "publisher": 1.0, "place": 1.0}
INFERRED_FIELDS = {"inferred_labels", "semantic_features", "image_type"}


def stem(token: str) -> str:
    if not token.isascii() or len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        token = token[:-3] + "y"
    elif token.endswith("sses"):
        token = token[:-2]
    elif token.endswith("s") and not token.endswith("ss"):
        token = token[:-1]
    for suffix in ("ists", "isms", "ist", "ism"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def tokenize(text: str | None) -> list[str]:
    if not text:
        return []
    return [stem(t) for t in re.findall(r"\w+", text.lower()) if t not in STOPWORDS]


@dataclass
class SearchQuery:
    text: str = ""
    kind: str = "images"                 # 'images' | 'pages'
    filters: dict = field(default_factory=dict)
    limit: int = 20


@dataclass
class SearchHit:
    id: str
    kind: str
    score: float
    title: str | None
    url: str
    source_page_url: str | None
    publisher: str | None
    matched_terms: list[str]
    missing_terms: list[str]
    explanation: list[str]
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


class SearchBackend(Protocol):
    name: str

    def search(self, query: SearchQuery) -> list[SearchHit]:
        ...


def score_document(terms: list[str], fields: dict[str, str], weights: dict[str, float]):
    tokens = {f: tokenize(text) for f, text in fields.items()}
    score, matched, why = 0.0, [], []
    for term in dict.fromkeys(terms):
        hit_fields = []
        for f, toks in tokens.items():
            tf = toks.count(term)
            if tf:
                score += weights[f] * (1 + math.log(tf))
                hit_fields.append(f + (" (inferred)" if f in INFERRED_FIELDS else ""))
        if hit_fields:
            matched.append(term)
            why.append(f"'{term}' in {', '.join(hit_fields)}")
    unique = list(dict.fromkeys(terms))
    coverage = len(matched) / len(unique) if unique else 1.0
    return round(score * coverage, 4), matched, [t for t in unique if t not in matched], why


class KeywordSearch:
    name = "keyword"

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def search(self, query: SearchQuery) -> list[SearchHit]:
        if query.kind == "pages":
            docs = self._page_docs(query.filters)
            weights = PAGE_FIELDS
        elif query.kind == "images":
            docs = self._image_docs(query.filters)
            weights = IMAGE_FIELDS
        else:
            raise ValueError("kind must be 'pages' or 'images'")
        terms = tokenize(query.text)
        hits = []
        for doc in docs:
            if terms:
                score, matched, missing, why = score_document(terms, doc["fields"], weights)
                if not matched:
                    continue
            else:
                score, matched, missing, why = 0.0, [], [], ["no query terms: filter match only"]
            hits.append(SearchHit(doc["id"], query.kind, score, doc["title"], doc["url"],
                                  doc.get("source_page_url"), doc.get("publisher"), matched,
                                  missing, why, doc.get("extra", {})))
        hits.sort(key=lambda h: (-h.score, h.id))
        return hits[: query.limit] if query.limit else hits

    def _page_docs(self, f: dict) -> list[dict]:
        from .pages import PageRepo
        rows = PageRepo(self.conn).all(source_id=f.get("source"), publisher=f.get("publisher"),
                                       category=f.get("category"), page_type=f.get("page_type"),
                                       language=f.get("language"))
        docs = []
        for r in rows:
            if r["crawl_status"] != "fetched":
                continue
            labels = [c["claim"] for c in r["analysis"].get("inferred", [])]
            if f.get("feature"):
                name, _, value = f["feature"].partition("=")
                feat = r["visual_features"].get(name, {})
                text = json.dumps(feat.get("value")) + " " + " ".join(
                    c["claim"] for c in r["analysis"].get("inferred", []) if c["feature"] == name)
                if feat.get("status") in (None, "unverified") and not any(
                        c["feature"] == name for c in r["analysis"].get("inferred", [])):
                    continue
                if value and value.lower() not in text.lower():
                    continue
            docs.append({
                "id": r["id"], "title": r["title"], "url": r["canonical_url"] or r["url"],
                "publisher": r["publisher"],
                "fields": {"title": r["title"], "keywords": " ".join(r["keywords"]),
                           "description": r["description"], "category": r["category"],
                           "inferred_labels": " ".join(labels),
                           "image_text": " ".join(filter(None, [a.get("alt") for a in r["assets"]])),
                           "publisher": r["publisher"]},
                "extra": {"page_type": r["page_type"], "source_id": r["source_id"],
                          "published_at": r["published_at"]},
            })
        return docs

    def _image_docs(self, f: dict) -> list[dict]:
        from .assets import AssetRepo
        from .research import GenreRepo
        genre_ids = None
        if f.get("genre"):
            genre_ids = GenreRepo(self.conn).with_descendants(f["genre"])
            if not genre_ids:
                return []
        rows = AssetRepo(self.conn).query(
            source=f.get("source"), status=f.get("status"), image_type=f.get("image_type"),
            year_from=f.get("year_from"), year_to=f.get("year_to"), country=f.get("country"),
            region=f.get("region"), genre_ids=genre_ids, media_type=f.get("media_type"),
            downloaded_only=bool(f.get("downloaded_only")))
        docs = []
        for r in rows:
            feats = self.conn.execute(
                """SELECT feature_type, feature_value, kind, review_status FROM visual_features
                   WHERE asset_id=? AND review_status <> 'rejected'""", (r["id"],)).fetchall()
            if f.get("feature"):
                name, _, value = f["feature"].partition("=")
                if not any(x["feature_type"] == name and (not value or value.lower() in x["feature_value"].lower())
                           for x in feats):
                    continue
            genres = [g["name"] for g in AssetRepo(self.conn).genres(r["id"])]
            page_title = None
            if r["reference_id"]:
                pt = self.conn.execute("SELECT title FROM refs WHERE id=?", (r["reference_id"],)).fetchone()
                page_title = pt[0] if pt else None
            semantic = " ".join(x["feature_value"] for x in feats if x["kind"] == "semantic")
            docs.append({
                "id": r["id"], "title": r["title"] or r["alt"], "url": r["url"],
                "source_page_url": r["source_page_url"], "publisher": r["publisher"],
                "fields": {"title": r["title"], "alt": r["alt"], "caption": r["caption"],
                           "description": r["description"], "genres": " ".join(genres),
                           "semantic_features": semantic, "image_type": r["image_type"].replace("_", " "),
                           "creator": r["creator"], "page_title": page_title,
                           "publisher": r["publisher"],
                           "place": " ".join(filter(None, [r["country"], r["region"]]))},
                "extra": {"image_type": r["image_type"], "type_status": r["type_status"],
                          "year_start": r["year_start"], "year_end": r["year_end"],
                          "country": r["country"], "download_status": r["download_status"],
                          "local_path": r["abs_path"] if r["download_status"] == "downloaded" else None,
                          "genres": genres},
            })
        return docs
