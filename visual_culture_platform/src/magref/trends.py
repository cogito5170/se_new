"""Descriptive comparisons over THIS collection -- never claims about culture at large.

Every result carries: the filter that defined the sample, sample sizes, how many
assets lacked the feature or a year, the source distribution, a minimum sample
threshold, and a limitations statement. When a group is below the threshold the
result says "insufficient sample" and states no direction of change.

Features are compared only from `visual_features` rows that are measured or
human-entered/reviewed; AI suggestions are excluded unless explicitly included.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter

from .assets import AssetRepo
from .research import GenreRepo
from .timeutil import utcnow

MIN_SAMPLE = 10
TRUSTED_REVIEW = ("auto_measured", "human_entered", "human_reviewed")


def _assets(conn, *, year_from=None, year_to=None, genre=None, country=None, region=None,
            source=None, media_type=None) -> list[dict]:
    genre_ids = GenreRepo(conn).with_descendants(genre) if genre else None
    if genre and not genre_ids:
        return []
    return AssetRepo(conn).query(year_from=year_from, year_to=year_to, genre_ids=genre_ids,
                                 country=country, region=region, source=source,
                                 media_type=media_type)


def _feature_values(conn, asset_ids: list[str], feature_type: str,
                    include_ai: bool) -> dict[str, list[str]]:
    if not asset_ids:
        return {}
    statuses = TRUSTED_REVIEW + (("ai_suggested",) if include_ai else ())
    out: dict[str, list[str]] = {}
    for chunk_start in range(0, len(asset_ids), 500):
        chunk = asset_ids[chunk_start:chunk_start + 500]
        rows = conn.execute(
            f"""SELECT asset_id, feature_value FROM visual_features
                WHERE feature_type=? AND review_status IN ({', '.join('?' * len(statuses))})
                AND asset_id IN ({', '.join('?' * len(chunk))})""",
            (feature_type, *statuses, *chunk)).fetchall()
        for r in rows:
            out.setdefault(r[0], []).append(r[1])
    return out


def _limitations(extra: list[str] | None = None) -> list[str]:
    base = [
        "Describes only the assets collected in this database; the collection is not a "
        "representative sample of any culture, period, genre or region.",
        "Source distribution shapes the result: one archive or publisher can dominate a period.",
        "Assets without a known year are excluded from period groups (not assigned by guess).",
        "Co-occurrence of a feature and a period does not establish cause or influence.",
    ]
    return base + (extra or [])


def summarize(conn, feature_type: str, *, include_ai: bool = False, min_sample: int = MIN_SAMPLE,
              **filters) -> dict:
    assets = _assets(conn, **filters)
    ids = [a["id"] for a in assets]
    values = _feature_values(conn, ids, feature_type, include_ai)
    counts = Counter(v for vals in values.values() for v in set(vals))
    with_feature = len(values)
    return {
        "filters": {k: v for k, v in filters.items() if v is not None},
        "feature_type": feature_type,
        "sample_size": len(assets),
        "with_feature": with_feature,
        "missing_feature": len(assets) - with_feature,
        "undated": sum(1 for a in assets if a["year_start"] is None),
        "sources": dict(Counter(a["source_id"] for a in assets).most_common()),
        "values": [{"value": v, "count": c, "share": round(c / with_feature, 3) if with_feature else None}
                   for v, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))],
        "sufficient": with_feature >= min_sample,
        "min_sample": min_sample,
        "asset_ids": ids,
    }


def compare_periods(conn, feature_type: str, period_a: tuple[int, int], period_b: tuple[int, int],
                    *, include_ai: bool = False, min_sample: int = MIN_SAMPLE, **filters) -> dict:
    a = summarize(conn, feature_type, year_from=period_a[0], year_to=period_a[1],
                  include_ai=include_ai, min_sample=min_sample, **filters)
    b = summarize(conn, feature_type, year_from=period_b[0], year_to=period_b[1],
                  include_ai=include_ai, min_sample=min_sample, **filters)
    rows = []
    for v in sorted({x["value"] for x in a["values"]} | {x["value"] for x in b["values"]}):
        sa = next((x["share"] for x in a["values"] if x["value"] == v), 0.0) if a["with_feature"] else None
        sb = next((x["share"] for x in b["values"] if x["value"] == v), 0.0) if b["with_feature"] else None
        rows.append({"value": v, "share_a": sa, "share_b": sb,
                     "difference": round(sb - sa, 3) if sa is not None and sb is not None else None})
    sufficient = a["sufficient"] and b["sufficient"]
    if sufficient:
        moved = sorted((r for r in rows if r["difference"] is not None),
                       key=lambda r: -abs(r["difference"]))[:3]
        statement = (f"In this collection ({a['with_feature']} vs {b['with_feature']} assets with "
                     f"'{feature_type}'), the largest share changes from {period_a[0]}-{period_a[1]} "
                     f"to {period_b[0]}-{period_b[1]} are: "
                     + "; ".join(f"{r['value']} {r['share_a']:.0%} -> {r['share_b']:.0%}" for r in moved)
                     + ". Descriptive only; no significance test.")
    else:
        statement = (f"Insufficient sample (need >= {min_sample} assets with '{feature_type}' in each "
                     f"period; have {a['with_feature']} and {b['with_feature']}). No trend is asserted.")
    return {"kind": "period_comparison", "feature_type": feature_type,
            "period_a": {"years": list(period_a), **a}, "period_b": {"years": list(period_b), **b},
            "rows": rows, "sufficient": sufficient, "statement": statement,
            "limitations": _limitations(), "generated_at": utcnow()}


def frequency_by(conn, feature_type: str, group_by: str, *, include_ai: bool = False,
                 min_sample: int = MIN_SAMPLE, **filters) -> dict:
    """Feature value frequency per genre | country | region | decade | source."""
    if group_by not in ("genre", "country", "region", "decade", "source"):
        raise ValueError("group_by must be genre|country|region|decade|source")
    assets = _assets(conn, **filters)
    values = _feature_values(conn, [a["id"] for a in assets], feature_type, include_ai)
    groups: dict[str, list[dict]] = {}
    for a in assets:
        if group_by == "genre":
            keys = [g["name"] for g in AssetRepo(conn).genres(a["id"])] or ["(no genre)"]
        elif group_by == "decade":
            keys = [f"{(a['year_start'] // 10) * 10}s"] if a["year_start"] is not None else ["(undated)"]
        elif group_by == "source":
            keys = [a["source_id"]]
        else:
            keys = [a[group_by] or f"(no {group_by})"]
        for k in keys:
            groups.setdefault(k, []).append(a)
    table = []
    for key in sorted(groups):
        members = groups[key]
        vals = [values[m["id"]] for m in members if m["id"] in values]
        counts = Counter(v for vs in vals for v in set(vs))
        table.append({"group": key, "sample_size": len(members), "with_feature": len(vals),
                      "sufficient": len(vals) >= min_sample,
                      "values": [{"value": v, "count": c, "share": round(c / len(vals), 3)}
                                 for v, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]})
    return {"kind": "frequency", "feature_type": feature_type, "group_by": group_by,
            "filters": {k: v for k, v in filters.items() if v is not None}, "groups": table,
            "limitations": _limitations(["Groups below the minimum sample are shown but must not "
                                         "be read as a pattern."]),
            "min_sample": min_sample, "generated_at": utcnow()}


def emergence(conn, feature_type: str, value: str, *, bucket: int = 10, include_ai: bool = False,
              min_sample: int = MIN_SAMPLE, **filters) -> dict:
    """Share of assets with feature=value per time bucket; flags only well-sampled changes."""
    assets = [a for a in _assets(conn, **filters) if a["year_start"] is not None]
    values = _feature_values(conn, [a["id"] for a in assets], feature_type, include_ai)
    buckets: dict[int, list[str]] = {}
    for a in assets:
        if a["id"] in values:
            buckets.setdefault((a["year_start"] // bucket) * bucket, []).append(a["id"])
    series = []
    for start in sorted(buckets):
        ids = buckets[start]
        hit = sum(1 for i in ids if value in values[i])
        series.append({"from": start, "to": start + bucket - 1, "with_feature": len(ids),
                       "matches": hit, "share": round(hit / len(ids), 3),
                       "sufficient": len(ids) >= min_sample})
    first = next((s for s in series if s["matches"]), None)
    increases = []
    for prev, cur in zip(series, series[1:]):
        if prev["sufficient"] and cur["sufficient"] and cur["share"] > prev["share"]:
            increases.append({"from_bucket": prev["from"], "to_bucket": cur["from"],
                              "share_change": round(cur["share"] - prev["share"], 3)})
    return {"kind": "emergence", "feature_type": feature_type, "value": value, "bucket_years": bucket,
            "series": series,
            "first_seen_in_collection": first["from"] if first else None,
            "increases_between_well_sampled_buckets": increases,
            "note": "'First seen' is the earliest bucket in THIS collection, not a historical first.",
            "limitations": _limitations(), "generated_at": utcnow()}


def common_features(conn, genres: list[str], feature_type: str, *, threshold: float = 0.5,
                    include_ai: bool = False, min_sample: int = MIN_SAMPLE, **filters) -> dict:
    per = {g: summarize(conn, feature_type, genre=g, include_ai=include_ai, min_sample=min_sample,
                        **filters) for g in genres}
    common = []
    candidates = set.intersection(*[{v["value"] for v in s["values"]} for s in per.values()]) if per else set()
    for v in sorted(candidates):
        shares = {g: next(x["share"] for x in s["values"] if x["value"] == v) for g, s in per.items()}
        if all(sh is not None and sh >= threshold for sh in shares.values()):
            common.append({"value": v, "shares": shares})
    return {"kind": "common_features", "feature_type": feature_type, "genres": genres,
            "threshold": threshold, "common": common,
            "samples": {g: {"sample_size": s["sample_size"], "with_feature": s["with_feature"],
                            "sufficient": s["sufficient"]} for g, s in per.items()},
            "note": "Shared features do not show influence between genres; that needs separate evidence.",
            "limitations": _limitations(), "generated_at": utcnow()}


def timeline(conn, *, year_from: int | None = None, year_to: int | None = None, bucket: int = 1,
             **filters) -> dict:
    assets = _assets(conn, year_from=year_from, year_to=year_to, **filters)
    dated = [a for a in assets if a["year_start"] is not None]
    rows: dict[int, dict] = {}
    for a in dated:
        key = (a["year_start"] // bucket) * bucket
        r = rows.setdefault(key, {"from": key, "to": key + bucket - 1, "count": 0, "sources": Counter(),
                                  "asset_ids": []})
        r["count"] += 1
        r["sources"][a["source_id"]] += 1
        r["asset_ids"].append(a["id"])
    from .research import ContextRepo
    contexts = ContextRepo(conn).search(year_from=year_from, year_to=year_to)
    return {"kind": "timeline", "bucket_years": bucket,
            "rows": [dict(r, sources=dict(r["sources"])) for _, r in sorted(rows.items())],
            "undated_in_filter": len(assets) - len(dated) if year_from is None and year_to is None else None,
            "contexts": [{"id": c["id"], "title": c["title"], "start_year": c["start_year"],
                          "end_year": c["end_year"], "verification_status": c["verification_status"]}
                         for c in contexts],
            "limitations": _limitations()}


def save_observation(conn: sqlite3.Connection, result: dict, title: str) -> int:
    """Persist a comparison as a TrendObservation (always starts 'unverified')."""
    if result.get("kind") == "period_comparison":
        start, end = result["period_a"]["years"][0], result["period_b"]["years"][1]
        sample = result["period_a"]["with_feature"] + result["period_b"]["with_feature"]
        ids = result["period_a"]["asset_ids"] + result["period_b"]["asset_ids"]
        observed = {"statement": result["statement"], "rows": result["rows"],
                    "sufficient": result["sufficient"]}
        filters = result["period_a"]["filters"]
    else:
        raise ValueError("only period comparisons can be saved as observations")
    genre_id = None
    if filters.get("genre"):
        g = GenreRepo(conn).get(filters["genre"])
        genre_id = g["id"] if g else None
    with conn:
        cur = conn.execute(
            """INSERT INTO trend_observations (title, genre_id, start_year, end_year, region,
               feature_definition, sample_size, observed_result, method, limitations,
               source_asset_ids, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (title, genre_id, start, end, filters.get("region") or filters.get("country"),
             f"visual_features.feature_type = '{result['feature_type']}' (trusted review statuses)",
             sample, json.dumps(observed, ensure_ascii=False), "share of assets per value; two periods",
             "\n".join(result["limitations"]), json.dumps(sorted(set(ids))), utcnow()))
    return cur.lastrowid
