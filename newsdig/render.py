"""**찍기.** 레이아웃은 코드가 찍는다 -- 모델이 틀을 기억할 필요가 없다.

인지과학 근거(초두 효과 · 청킹 4 · 같은 꼴 반복 · 앞머리에 핵심어 · 주장 바로 아래 출처 ·
뺄셈 대신 '3시간 전')는 여기 박혀 있다. 모델은 칸만 채운다.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from newsdig.gate import parse_time

KST = timezone(timedelta(hours=9))
LABEL = {"tech": "TECH", "techart": "TECH ART"}


def flag(cc: str) -> str:
    cc = (cc or "").upper()
    if len(cc) != 2 or not cc.isalpha():
        return "🌐"
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in cc)


def ago(t: datetime | None, now: datetime) -> str:
    if t is None:
        return "시각 미상"
    m = int((now - t).total_seconds() // 60)
    if m < 60:
        return f"{max(m, 1)}분 전"
    if m < 48 * 60:
        return f"{m // 60}시간 전"
    return f"{m // 1440}일 전"


def render(work: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    gate = json.loads((work / "gate.json").read_text(encoding="utf-8"))
    items = {i["id"]: i for i in json.loads((work / "items.json").read_text(encoding="utf-8"))["items"]}
    meta = json.loads((work / "items.json").read_text(encoding="utf-8"))
    cands = {}
    for line in (work / "candidates.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            c = json.loads(line)
            cands[c["id"]] = c
    head = f"📅 {now.astimezone(KST):%m/%d %H:%M}"
    out = [head, "", "**⚡ 3줄 요약**"]
    for n, s in enumerate(meta.get("summary", [])[:3], 1):
        out.append(f"{n}. {s['text']}")
    for sec in ("tech", "techart"):
        chosen = [items[i] for i in gate["chosen"] if (items[i].get("section") or cands[i]["section"]) == sec]
        if not chosen:
            continue
        out += ["", f"**━ {LABEL[sec]} ━**"]
        for n, it in enumerate(chosen, 1):
            c = cands[it["id"]]
            out += ["", f"**{n}. {it['title']}**", f"· {it['what']}", f"· → {it['why']}",
                    f"↳ {flag(c['country'])} [{c['outlet']}]({c['url']}) · {ago(parse_time(gate.get('times', {}).get(it['id'], '')) or parse_time(c['published']), now)}"]
    out += ["", "**━ 관찰 ━**", meta.get("observation", "")]
    lg = gate["log"]
    fails = ", ".join(lg["failed_doors"][:6]) + (" …" if len(lg["failed_doors"]) > 6 else "")
    tail = (f"게이트: 후보 {lg['candidates']} (지역 {lg['regions']}곳 · 언어 {lg['langs']}개) → "
            f"원문 대상 {lg['candidates'] - lg.get('cand_stale', 0)} (낡은 후보 {lg.get('cand_stale', 0)} 제외) → 통과 {lg['passed']} · 표시 {lg['shown']} (오래됨 {lg['stale']} · 원문 미확인 {lg['unverified']}"
            f" · 불일치 {lg['mismatch']} · 형식 {lg['form']}) · 창 tech/art {gate['window_h']}h")
    if fails:
        tail += f" · 실패한 문: {fails}"
    if lg["notes"]:
        tail += f" · 모자람: {', '.join(lg['notes'])}"
    out += ["", f"`{tail}`"]
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    print(render(Path(sys.argv[1] if len(sys.argv) > 1 else "newsdig/work")))
