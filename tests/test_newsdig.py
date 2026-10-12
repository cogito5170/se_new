"""newsdig 배선 검사. 망을 안 탄다 -- 가짜 모델이 파일을 채우고 step/gate/render 를 끝까지 돈다.

붙드는 것 (이 관문이 있는 까닭 그대로):
  · 원문을 안 열었으면(B002) 못 나간다
  · 원문에 없는 숫자(B004)는 못 나간다
  · 문 원문에 없는 주소(B006)는 후보가 못 된다
  · 낡은 기사(B003)는 못 나간다
  · 끝까지 가면 FINAL 과 고정된 레이아웃이 나온다
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from newsdig import gate as GT     # noqa: E402
from newsdig import step as ST     # noqa: E402

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
CC = ["JP", "DE", "US", "KR", "FR", "IN"]


def _step() -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        ST.main()
    return buf.getvalue()


def _fill_doors(work: Path):
    doors = json.loads((work / "doors.json").read_text())
    for d in doors:
        if d["name"] == "weather":
            body = '{"current_condition":[{"temp_C":"17","weatherDesc":[{"value":"Clear"}]}]}'
        else:
            body = "\n".join(f"Story {d['id']}-{k} | https://news{k}.example/{d['id']}/{k} | 2026-10-12T09:00:00Z"
                             for k in range(2))
        (work / "doors" / f"{d['id']}.txt").write_text(f"URL: {d['target']}\n{body}")
    return doors


def _cands(doors, n=16, age_h=3):
    out = []
    for i in range(n):
        d = doors[i]
        out.append({"id": f"C{i:03d}", "title": f"Story {d['id']}-0", "url": f"https://news0.example/{d['id']}/0",
                    "outlet": f"Outlet{i}", "country": CC[i % len(CC)], "lang": "en",
                    "published": (NOW - timedelta(hours=age_h)).isoformat(),
                    "section": "tech" if i % 2 == 0 else "techart", "door": d["id"]})
    return out


ARTICLE = ("Headline\n2026-10-12\nThe Kyoto lab unveiled a 128-core research chip on Monday, "
           "claiming 40 percent lower power than its previous design. " + "Filler sentence. " * 30)


def _items(ids):
    items = []
    for r, i in enumerate(ids):
        items.append({"id": i, "rank": r + 1, "title": "128코어 연구 칩 공개", "what": "Kyoto 연구실이 128코어 칩을 공개했다",
                      "why": "전력을 40% 줄였다고 밝혔다", "evidence": ["unveiled a 128-core research chip on Monday"]})
    return {"items": items, "summary": [{"id": ids[k], "text": f"128코어 칩 {k}"} for k in range(3)],
            "observation": "연구실 칩이 전력을 줄였다."}


def _run(mutate=None):
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "work"
        ST.WORK = work
        real_now = ST.datetime

        class _DT(datetime):
            @classmethod
            def now(cls, tz=None):
                return NOW
        ST.datetime = _DT
        try:
            assert "STEP doors" in _step()
            doors = _fill_doors(work)
            assert "STEP weather" in _step()
            wd = next(d for d in doors if d["name"] == "weather")
            (work / "weather.json").write_text(json.dumps({"temp_c": 17, "desc": "맑음", "tip": "얇은 겉옷"}))
            assert "STEP candidates" in _step()
            cands = _cands(doors)
            if mutate == "invented_url":
                cands[0]["url"] = "https://made.up/zzz"
                cands[0]["title"] = "nothing like it"
            if mutate == "stale":
                for c in cands:
                    c["published"] = (NOW - timedelta(hours=60)).isoformat()
            (work / "candidates.jsonl").write_text("\n".join(json.dumps(c) for c in cands))
            out = _step()
            if mutate == "invented_url":
                assert "지어낸 후보" in out, out
                return "caught"
            if mutate == "stale":
                # 열 것이 없다 -> 지어내지 않고 빈 회차로 끝난다
                assert out.startswith("FINAL") and "통과 0" in out and "오래됨" in out, out
                return "caught"
            assert "STEP articles" in out, out
            picked = json.loads((work / "picked.json").read_text())
            for i in picked:
                if mutate == "unopened" and i in picked[:3]:
                    (work / "articles" / f"{i}.fail").write_text("403")
                    continue
                url = next(c["url"] for c in cands if c["id"] == i)
                (work / "articles" / f"{i}.txt").write_text(f"URL: {url}\n{ARTICLE}")
            assert "STEP items" in _step()
            ids = picked[:8]
            data = _items(ids)
            if mutate == "bad_number":
                for it in data["items"]:
                    it["why"] = "전력을 55% 줄였다고 밝혔다"
            (work / "items.json").write_text(json.dumps(data, ensure_ascii=False))
            out = _step()
            if mutate == "bad_number":
                assert "B004 숫자 '55'" in out, out
                return "caught"
            if mutate == "unopened":
                assert "STEP fix items" in out and "B002" in out, out
                return "caught"
            assert out.startswith("FINAL"), out
            for must in ("**⚡ 3줄 요약**", "**━ TECH ━**", "**━ TECH ART ━**", "**━ 관찰 ━**", "게이트:", "3시간 전", "17°C"):
                assert must in out, must
            return "final"
        finally:
            ST.datetime = real_now


def test_happy_path():
    assert _run() == "final"


def test_invented_url_rejected():
    assert _run("invented_url") == "caught"


def test_number_not_in_article_rejected():
    assert _run("bad_number") == "caught"


def test_unopened_article_rejected():
    assert _run("unopened") == "caught"


def test_stale_not_opened():
    assert _run("stale") == "caught"


if __name__ == "__main__":
    for f in (test_happy_path, test_invented_url_rejected, test_number_not_in_article_rejected,
              test_unopened_article_rejected, test_stale_not_opened):
        f()
        print("ok", f.__name__)
