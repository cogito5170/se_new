"""**다음 한 걸음.** 회차의 상태를 보고 지금 할 일 **하나만** 짧게 말한다.

가벼운 모델에게 긴 지시문을 통째로 주면 뒤쪽 규칙을 놓친다. 그래서 순서와 규칙을
코드가 쥐고, 모델은 `python3 newsdig/step.py` 를 부르고 → 시킨 것을 하고 → 다시 부른다.
무엇을 빠뜨렸는지는 파일이 말해 준다(문 파일 · 후보 · 원문 · 항목). 기억에 안 기댄다.

끝나면 `FINAL` 아래에 보낼 글을 찍는다. 모델은 그것을 **그대로** 낸다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsdig import doors as DR          # noqa: E402
from newsdig import gate as GT           # noqa: E402
from newsdig import render as RD         # noqa: E402

WORK = Path(__file__).resolve().parent / "work"
BATCH_DOORS = 8
BATCH_ARTICLES = 6
MAX_ARTICLES = 30
MAX_TRIES = 3

FEED_PROMPT = ("List every article or story on this page, one per line, as: "
               "title | full url | publish time (ISO 8601 with timezone if shown) | outlet | language. "
               "No commentary, no summary.")
ARTICLE_PROMPT = ("Return: line 1 the headline, line 2 the publish date/time exactly as shown, "
                  "then the full article text verbatim. Do not summarize or paraphrase.")


def _save_rule(path: str, url: str) -> str:
    return (f"Write tool → `{path}`: first line `URL: {url}` then the tool output verbatim. "
            f"If it errors or is blocked, Write `{path[:-4]}.fail` with the reason (403/404/429/timeout/declined).")


def doors_step(doors: list[dict]) -> str | None:
    todo = [d for d in doors if not (WORK / "doors" / f"{d['id']}.txt").is_file()
            and not (WORK / "doors" / f"{d['id']}.fail").is_file()]
    if not todo:
        return None
    lines = [f"STEP doors ({len(doors) - len(todo)}/{len(doors)} done). Do these {min(len(todo), BATCH_DOORS)} now, "
             "in parallel if you can, then run step.py again."]
    for d in todo[:BATCH_DOORS]:
        p = f"newsdig/work/doors/{d['id']}.txt"
        if d["kind"] == "search":
            lines.append(f"- {d['id']} WebSearch query=\"{d['target']}\". " + _save_rule(p, "search:" + d["target"]))
        else:
            prompt = "Return the JSON exactly as received." if d["name"] == "weather" else FEED_PROMPT
            lines.append(f"- {d['id']} WebFetch url={d['target']} prompt=\"{prompt}\". " + _save_rule(p, d["target"]))
    return "\n".join(lines)


def weather_step(doors: list[dict]) -> str | None:
    wd = next(d for d in doors if d["name"] == "weather")
    wf = WORK / "weather.json"
    if wf.is_file():
        # 기온이 받은 원문에 실제로 있는가 -- 지어낸 날씨는 화면에 못 나간다
        try:
            w = json.loads(wf.read_text(encoding="utf-8"))
        except ValueError:
            w = None
        src = WORK / "doors" / f"{wd['id']}.txt"
        if w == {} or (w and src.is_file() and str(w.get("temp_c")) in src.read_text(encoding="utf-8")):
            return None
        wf.write_text("{}", encoding="utf-8")
        return None
    if (WORK / "doors" / f"{wd['id']}.fail").is_file():
        (WORK / "weather.json").write_text("{}", encoding="utf-8")
        return None
    return ("STEP weather. From newsdig/work/doors/" + wd["id"] + ".txt take the current Seoul temperature (°C) "
            "and condition. Write `newsdig/work/weather.json` as "
            '{"temp_c": <number from the file>, "desc": "<Korean 2~4자, e.g. 맑음>", "tip": "<Korean 외출 팁 12자 이내>"}. '
            "Then run step.py again.")


CAND_SCHEMA = ('{"id":"C001","title":"…","url":"https://…","outlet":"…","country":"JP","lang":"ja",'
               '"published":"2026-10-12T09:00:00+09:00","section":"tech|techart","door":"D03"}')


def candidates_step(st: dict) -> str | None:
    errs = GT.check_candidates(st) if st["cands"] else ["candidates.jsonl 가 아직 없다"]
    n = len(st["cands"])
    if not errs and n >= 15:
        return None
    return ("STEP candidates. Read the files in newsdig/work/doors/*.txt and Write `newsdig/work/candidates.jsonl`: "
            "one JSON object per line for EVERY dated article you see there (aim 40+, both sections, many countries; "
            "do not judge importance). Each line exactly: " + CAND_SCHEMA + ". url and title must be copied from the "
            "door file; door = the file it came from; country = outlet's country code; drop items with no date. "
            f"Now {n} candidates. Fix these, rewrite the whole file, run step.py again:\n- "
            + "\n- ".join(errs[:15] or [f"need at least 15 candidates (have {n})"]))


def pick(st: dict, now: datetime) -> list[str]:
    """원문을 열 후보를 코드가 고른다: 36시간 안 · 갈래와 나라를 돌아가며."""
    fresh = []
    for c in st["cands"].values():
        t = GT.parse_time(c.get("published", ""))
        if t and timedelta(hours=-2) < now - t < timedelta(hours=GT.STALE_H):
            fresh.append((now - t, c))
    fresh.sort(key=lambda x: x[0])
    picked, seen = [], {}
    for rnd in range(10):
        for _, c in fresh:
            key = (c["section"], c["country"].upper())
            if c["id"] in picked or seen.get(key, 0) > rnd:
                continue
            seen[key] = seen.get(key, 0) + 1
            picked.append(c["id"])
            if len(picked) >= MAX_ARTICLES:
                return picked
    return picked


def articles_step(st: dict, now: datetime) -> str | None:
    pf = WORK / "picked.json"
    if not pf.is_file():
        pf.write_text(json.dumps(pick(st, now)), encoding="utf-8")
    picked = json.loads(pf.read_text(encoding="utf-8"))
    todo = [i for i in picked if not (WORK / "articles" / f"{i}.txt").is_file()
            and not (WORK / "articles" / f"{i}.fail").is_file()]
    if not todo:
        return None
    lines = [f"STEP articles ({len(picked) - len(todo)}/{len(picked)} done). Open these now, then run step.py again. "
             "If one is blocked, try a side door first (amp page, m. host, or the same story on another outlet) and put "
             "`VIA: <that url>` on line 2; the first line stays the original URL."]
    for i in todo[:BATCH_ARTICLES]:
        url = st["cands"][i]["url"]
        lines.append(f"- {i} WebFetch url={url} prompt=\"{ARTICLE_PROMPT}\". "
                     + _save_rule(f"newsdig/work/articles/{i}.txt", url))
    return "\n".join(lines)


ITEM_SCHEMA = ('{"items":[{"id":"C001","section":"tech","rank":1,"title":"…≤25자","what":"…≤40자",'
               '"why":"…≤40자","evidence":["verbatim sentence copied from articles/C001.txt (20+ chars)"],'
               '"speculative":false}],"summary":[{"id":"C001","text":"…≤22자"},{…},{…}],"observation":"…≤160자"}')


def items_step(st: dict, now: datetime) -> str | None:
    fetched = sorted(p.stem for p in (WORK / "articles").glob("*.txt"))
    if not fetched and not (WORK / "items.json").is_file():
        # 열 것이 없었다(전부 낡았거나 전부 막혔다). 지어내지 않고 빈 회차로 끝낸다.
        (WORK / "items.json").write_text(json.dumps({
            "items": [], "summary": [],
            "observation": "이번 회차는 관문을 통과한 기사가 없다 -- 아래 게이트 줄이 까닭이다."},
            ensure_ascii=False), encoding="utf-8")
        return None
    tries_f = WORK / "tries.txt"
    tries = int(tries_f.read_text()) if tries_f.is_file() else 0
    if (WORK / "items.json").is_file():
        r = GT.run(WORK, now)
        if r["ok"] and not r["item_errors"]:
            return None
        if tries >= MAX_TRIES and len(r["chosen"]) >= 4:
            return None
        if tries >= MAX_TRIES + 2:
            return None
        tries_f.write_text(str(tries + 1))
        errs = r["candidate_errors"] + r["item_errors"] + r["summary_errors"] + r["soft"]
        return (f"STEP fix items (try {tries + 1}). The gate rejected these. Edit `newsdig/work/items.json` "
                "(fix the wording to match the article, or drop the item), then run step.py again:\n- "
                + "\n- ".join(errs[:20]) + f"\nPassing now: {r['log']['passed']}, shown: {r['chosen']}")
    lines = [
        "STEP items. Read newsdig/work/articles/*.txt and Write `newsdig/work/items.json` in Korean.",
        "Use 8~12 of these ids (both sections, many countries, things the reader has not seen): " + ", ".join(fetched),
        "Rules the gate enforces: every number and every Latin-letter name you write must appear in that article; "
        "evidence = 1~2 sentences copied character-for-character from the article file; title starts with the key "
        "noun or number; rank 1 = most important within its section; summary = 3 lines about shown items; "
        "speculation needs \"(추정)\". Shape:",
        ITEM_SCHEMA,
        "Then run step.py again.",
    ]
    return "\n".join(lines)


def main() -> int:
    now = datetime.now(timezone.utc)
    for sub in ("doors", "articles"):
        (WORK / sub).mkdir(parents=True, exist_ok=True)
    df = WORK / "doors.json"
    if not df.is_file():
        df.write_text(json.dumps(DR.build(now), ensure_ascii=False, indent=1), encoding="utf-8")
    doors = json.loads(df.read_text(encoding="utf-8"))
    msg = doors_step(doors) or weather_step(doors)
    if msg:
        print(msg)
        return 0
    st = GT.load(WORK)
    msg = candidates_step(st) or articles_step(st, now) or items_step(st, now)
    if msg:
        print(msg)
        return 0
    GT.run(WORK, now)
    print("FINAL — send the text below as your whole final message, unchanged:\n")
    print(RD.render(WORK, now))
    from newsdig import usage as US
    print("`" + US.line(US.measure()) + "`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
