"""**관문.** 모델이 쓴 항목을 코드가 다시 본다. LLM 이 아니다.

brief/gate.py 의 B001~B005 를 뉴스로 옮겼다. 가벼운 모델은 긴 지시문의 규칙을 다
지키지 않는다 -- 그래서 규칙을 지시문에서 빼서 **여기로 옮겼다.** 모델이 무엇을 쓰든
여기를 못 지나면 화면에 안 나간다.

    B001  출처 주소가 있는가                                    hard
    B002  그 주소를 이 회차에 **실제로 열었는가** -- articles/  hard
          그리고 근거 발췌가 그 원문에 글자 그대로 있는가
    B003  신선한가 (기본 12시간, 모자라면 36시간)               hard
    B004  제목·요지에 쓴 숫자와 라틴 고유명이 원문에 있는가      hard
    B005  근거 없이 단정하는 말                                 soft
    B006  후보가 문(doors/)에서 왔는가 -- 지어낸 주소가 아닌가   hard
    L001  길이 · 갈래 · 지역 꼴                                 hard

**이 관문이 못 보는 것**: 원문 해석이 옳은지, 그 기사가 중요한지. 앞은 사람이 원문
링크로 확인하고, 뒤는 기계의 관할이 아니다.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 갈래마다 (좁은 창, 넓은 창) 시간. 좁은 창으로 5개가 안 차면 넓힌다.
# 예술 매체는 주간지 박자다 -- 실측 2026-10-12: 예술 피드의 최신 글이 3~6일 전이었다.
WINDOW = {"tech": (12, 36), "techart": (72, 168)}
STALE_H = max(w[1] for w in WINDOW.values())
UNKNOWN = "unknown"
MAX_LEN = {"title": 25, "what": 40, "why": 40}
SUMMARY_LEN = 22
OBS_LEN = 160
EVIDENCE_MIN = 20
SECTIONS = ("tech", "techart")
SOFT_WORDS = ("세계 최초", "최초", "유일", "역대", "혁명", "완전히", "압도적", "판도를 바꿀")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace(" ", " ").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def _digits(s: str) -> str:
    return re.sub(r"(?<=\d)[,.](?=\d{3}\b)", "", _norm(s))


_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_loose(text: str) -> datetime | None:
    """원문 머리에서 날짜 하나를 줍는다. 시각이 없으면 그날 00:00 UTC 로 둔다."""
    head = (text or "")[:600]
    m = re.search(r"(20\d\d)[-./년 ]\s*(\d{1,2})[-./월 ]\s*(\d{1,2})", head)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"([A-Za-z]{3,9})\.? (\d{1,2}),? (20\d\d)", head)
        m2 = None if m else re.search(r"(\d{1,2}) ([A-Za-z]{3,9})\.? (20\d\d)", head)
        if m and m.group(1)[:3].lower() in _MONTHS:
            mo, d, y = _MONTHS[m.group(1)[:3].lower()], int(m.group(2)), int(m.group(3))
        elif m2 and m2.group(2)[:3].lower() in _MONTHS:
            d, mo, y = int(m2.group(1)), _MONTHS[m2.group(2)[:3].lower()], int(m2.group(3))
        else:
            return None
    try:
        return datetime(y, mo, d, tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_time(s: str) -> datetime | None:
    if not s or s.strip().lower() == UNKNOWN:
        return None
    s = s.strip().replace("Z", "+00:00")
    for fmt in (None, "%Y%m%dT%H%M%S%z", "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            t = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def read_header(path: Path) -> tuple[str, str]:
    """첫 줄 `URL: ...` 를 떼고 (url, 본문) 을 낸다."""
    text = path.read_text(encoding="utf-8", errors="replace")
    first, _, rest = text.partition("\n")
    url = first[4:].strip() if first.upper().startswith("URL:") else ""
    return url, rest


def load(work: Path) -> dict:
    doors = json.loads((work / "doors.json").read_text(encoding="utf-8"))
    door_text, door_fail = {}, {}
    for d in doors:
        ok, bad = work / "doors" / f"{d['id']}.txt", work / "doors" / f"{d['id']}.fail"
        if ok.is_file():
            door_text[d["id"]] = ok.read_text(encoding="utf-8", errors="replace")
        elif bad.is_file():
            door_fail[d["id"]] = bad.read_text(encoding="utf-8", errors="replace").strip()[:60]
    cands = {}
    cpath = work / "candidates.jsonl"
    if cpath.is_file():
        for line in cpath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                c = json.loads(line)
                cands[c.get("id", "")] = c
    items = {}
    ipath = work / "items.json"
    if ipath.is_file():
        items = json.loads(ipath.read_text(encoding="utf-8"))
    return {"doors": doors, "door_text": door_text, "door_fail": door_fail,
            "cands": cands, "items": items}


def check_candidates(st: dict) -> list[str]:
    """B006: 후보마다 칸이 다 있고, 그 주소가 문 원문에 실제로 나왔는가."""
    errs = []
    need = ("id", "title", "url", "outlet", "country", "lang", "published", "section", "door")
    for cid, c in st["cands"].items():
        miss = [k for k in need if not str(c.get(k, "")).strip()]
        if miss:
            errs.append(f"{cid}: 칸 없음 {miss}")
            continue
        if c["section"] not in SECTIONS:
            errs.append(f"{cid}: section 은 tech|techart")
        if len(c["country"]) != 2:
            errs.append(f"{cid}: country 는 두 글자 코드(US, JP …)")
        if c["published"].strip().lower() != UNKNOWN and parse_time(c["published"]) is None:
            errs.append(f"{cid}: published 를 ISO 8601 로 (예 2026-10-12T09:00:00+09:00), 날짜가 안 보이면 \"unknown\"")
        src = st["door_text"].get(c["door"])
        if src is None:
            errs.append(f"{cid}: door {c['door']} 원문 파일이 없다")
        elif not _url_seen(c["url"], src) and not _norm(c["title"])[:30] in _norm(src):
            errs.append(f"{cid}: 주소도 제목도 {c['door']} 원문에 없다 -- 지어낸 후보는 못 들어간다")
    return errs


def _url_seen(url: str, text: str) -> bool:
    u = re.sub(r"^https?://(www\.)?", "", url.strip()).rstrip("/")
    return bool(u) and u[:60].lower() in text.lower()


def resolved_time(c: dict, work: Path) -> datetime | None:
    """후보의 게시 시각. 후보에 없으면(검색 결과) 원문 머리에서 줍는다."""
    t = parse_time(c.get("published", ""))
    if t is None:
        art = work / "articles" / f"{c.get('id')}.txt"
        if art.is_file():
            t = parse_loose(read_header(art)[1])
    return t


def check_item(it: dict, c: dict | None, work: Path, now: datetime, wide: bool) -> tuple[list[str], str]:
    """한 항목. (위반들, 갈래) -- 갈래는 게이트 로그용: stale|unverified|mismatch|form|ok."""
    iid = it.get("id", "?")
    if c is None:
        return [f"{iid}: candidates.jsonl 에 없는 id"], "form"
    errs = []
    for k, lim in MAX_LEN.items():
        v = str(it.get(k, "")).strip()
        if not v:
            errs.append(f"{iid}: {k} 가 비었다")
        elif len(v) > lim:
            errs.append(f"{iid}: {k} {len(v)}자 > {lim}자 -- 줄여라")
    if it.get("section", c["section"]) not in SECTIONS:
        errs.append(f"{iid}: section 은 tech|techart")
    if errs:
        return errs, "form"
    # B003
    stale_h = WINDOW.get(c["section"], WINDOW["tech"])[1 if wide else 0]
    t = resolved_time(c, work)
    if t is None:
        return [f"{iid}: B003 게시 시각을 후보에서도 원문에서도 못 찾았다"], "stale"
    if now - t > timedelta(hours=stale_h) or t - now > timedelta(hours=26):
        return [f"{iid}: B003 게시 {t:%Y-%m-%d %H:%M}Z -- {stale_h}시간 밖이거나 미래"], "stale"
    # B002
    art = work / "articles" / f"{iid}.txt"
    if not art.is_file():
        return [f"{iid}: B002 articles/{iid}.txt 가 없다 -- 원문을 WebFetch 로 열고 저장하라"], "unverified"
    aurl, body = read_header(art)
    if not aurl or _norm(aurl).rstrip("/") != _norm(c["url"]).rstrip("/"):
        return [f"{iid}: B002 articles/{iid}.txt 첫 줄 URL 이 후보 주소와 다르다"], "unverified"
    if len(body.strip()) < 300:
        return [f"{iid}: B002 원문이 300자 미만 -- 막혔으면 곁문(amp·m.·다른 매체)을 열어라"], "unverified"
    ev = it.get("evidence") or []
    nb = _norm(body)
    good = [e for e in ev if len(_norm(e)) >= EVIDENCE_MIN and _norm(e) in nb]
    if not good:
        return [f"{iid}: B002 evidence 에 원문 글자 그대로의 발췌({EVIDENCE_MIN}자 이상)가 하나도 없다"], "unverified"
    # B004
    written = " ".join(str(it.get(k, "")) for k in MAX_LEN)
    db = _digits(body)
    for num in set(re.findall(r"\d+(?:\.\d+)?", _digits(written))):
        if num not in db:
            errs.append(f"{iid}: B004 숫자 '{num}' 이 원문에 없다 -- 원문 값으로 고치거나 빼라")
    for name in set(re.findall(r"[A-Za-z][A-Za-z0-9\-\.&]{1,}", written)):
        if name.lower() not in nb:
            errs.append(f"{iid}: B004 이름 '{name}' 이 원문에 없다")
    if errs:
        return errs, "mismatch"
    return [], "ok"


def soft_warnings(it: dict) -> list[str]:
    if it.get("speculative"):
        return []
    text = " ".join(str(it.get(k, "")) for k in ("title", "what", "why"))
    return [f"{it.get('id')}: B005 '{w}' -- 원문이 그렇게 말하지 않으면 빼거나 (추정) 을 붙여라"
            for w in SOFT_WORDS if w in text and "(추정)" not in text]


def select(passed: list[dict], cands: dict) -> tuple[list[dict], list[str]]:
    """L001: 갈래당 3(최대 4), 지역 3곳 이상, 미국 절반 이하. 모델 순위(rank)를 따른다."""
    notes = []
    by = {s: sorted([p for p in passed if p["section"] == s], key=lambda x: x.get("rank", 99))
          for s in SECTIONS}
    chosen: list[dict] = []
    for s in SECTIONS:
        chosen += by[s][:3]
    # 한쪽이 모자라면 다른 쪽에서 4번째까지 채운다
    for s in SECTIONS:
        other = [x for x in SECTIONS if x != s][0]
        if len(by[s]) < 3 and len(by[other]) > 3:
            chosen += by[other][3:4]
    us = [x for x in chosen if cands[x["id"]]["country"].upper() == "US"]
    while len(us) * 2 > len(chosen) and us:
        drop = us.pop()
        spare = [p for p in passed if p not in chosen and p["section"] == drop["section"]
                 and cands[p["id"]]["country"].upper() != "US"]
        if not spare:
            break
        chosen[chosen.index(drop)] = spare[0]
    for s in SECTIONS:
        n = sum(1 for x in chosen if x["section"] == s)
        if n < 2:
            notes.append(f"{s} 통과 {n}개")
    regions = {cands[x["id"]]["country"].upper() for x in chosen}
    if len(regions) < 3:
        notes.append(f"지역 {len(regions)}곳")
    return chosen, notes


def run(work: Path, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    st = load(work)
    out = {"candidate_errors": check_candidates(st)}
    items = st["items"].get("items", [])
    for it in items:
        it.setdefault("section", st["cands"].get(it.get("id"), {}).get("section"))
    res = {}
    for wide in (False, True):
        res = {it.get("id"): check_item(it, st["cands"].get(it.get("id")), work, now, wide) for it in items}
        if sum(1 for e, k in res.values() if k == "ok") >= 5:
            break
    out["window_h"] = "/".join(str(WINDOW[s][1 if wide else 0]) for s in SECTIONS)
    out["times"] = {cid: t.isoformat() for cid, c in st["cands"].items() if (t := resolved_time(c, work))}
    passed = [it for it in items if res[it.get("id")][1] == "ok"]
    out["item_errors"] = [e for errs, _ in res.values() for e in errs]
    out["soft"] = [w for it in passed for w in soft_warnings(it)]
    chosen, notes = select(passed, st["cands"])
    ids = {x["id"] for x in chosen}
    summ = st["items"].get("summary", [])
    out["summary_errors"] = []
    if len(summ) != 3 or len({x.get("id") for x in summ}) != len(summ):
        out["summary_errors"].append("summary 는 서로 다른 항목 3줄")
    for s in summ:
        if s.get("id") not in ids:
            out["summary_errors"].append(f"summary {s.get('id')}: 화면에 나가는 항목이 아니다 (나가는 것: {sorted(ids)})")
        if len(str(s.get("text", ""))) > SUMMARY_LEN:
            out["summary_errors"].append(f"summary {s.get('id')}: {SUMMARY_LEN}자 넘음")
    obs = str(st["items"].get("observation", ""))
    if not obs or len(obs) > OBS_LEN:
        out["summary_errors"].append(f"observation 은 1~{OBS_LEN}자")
    kinds = [k for _, k in res.values()]
    langs = {c["lang"] for c in st["cands"].values() if c.get("lang")}
    regions = {c["country"].upper() for c in st["cands"].values() if c.get("country")}
    out["log"] = {
        "candidates": len(st["cands"]), "regions": len(regions), "langs": len(langs),
        "passed": len(passed), "shown": len(chosen),
        "stale": kinds.count("stale"), "unverified": kinds.count("unverified"),
        "mismatch": kinds.count("mismatch"), "form": kinds.count("form"),
        "cand_stale": sum(1 for c in st["cands"].values()
                          if (t := parse_time(c.get("published", ""))) is not None
                          and now - t > timedelta(hours=WINDOW.get(c.get("section"), WINDOW["tech"])[1])),
        "failed_doors": [f"{next(d['name'] for d in st['doors'] if d['id'] == k)}({v})"
                         for k, v in st["door_fail"].items()],
        "notes": notes,
    }
    out["chosen"] = [x["id"] for x in chosen]
    out["ok"] = (not out["candidate_errors"] and len(chosen) >= 4 and not out["summary_errors"])
    (work / "gate.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys
    r = run(Path(sys.argv[1] if len(sys.argv) > 1 else "newsdig/work"))
    for k in ("candidate_errors", "item_errors", "summary_errors", "soft"):
        for e in r[k]:
            print(f"[{k}] {e}")
    print(json.dumps(r["log"], ensure_ascii=False))
    print("OK" if r["ok"] else "NOT OK")
    sys.exit(0 if r["ok"] else 1)
