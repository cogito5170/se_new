"""**토큰 실측.** 이 회차가 실제로 쓴 토큰을 세션 기록에서 센다 -- 추정이 아니다.

Claude Code 는 응답마다 `~/.claude/projects/<자리>/<세션>.jsonl` 에 `message.usage` 를 남긴다.
한 응답이 내용 블록마다 여러 줄로 찍히므로 **message.id 로 겹침을 뺀다** (실측 2026-10-12:
77줄 중 서로 다른 응답 43개 -- 그냥 더하면 거의 두 배로 부풀었다).

못 세는 것: WebFetch 가 속에서 부르는 작은 모델의 토큰. 그 호출은 이 기록에 안 남는다.
"""
from __future__ import annotations

import json
from pathlib import Path

KEYS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")


def measure(root: Path | None = None) -> dict:
    root = root or Path.home() / ".claude" / "projects"
    seen: dict[str, dict] = {}
    models: set[str] = set()
    for f in root.glob("*/*.jsonl"):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            m = d.get("message")
            if isinstance(m, dict) and isinstance(m.get("usage"), dict):
                seen[m.get("id") or d.get("uuid") or str(len(seen))] = m["usage"]
                if m.get("model"):
                    models.add(m["model"])
    tot = {k: sum(int(u.get(k) or 0) for u in seen.values()) for k in KEYS}
    tot["responses"] = len(seen)
    tot["web_search"] = sum(int((u.get("server_tool_use") or {}).get("web_search_requests") or 0) for u in seen.values())
    tot["models"] = sorted(models)
    tot["processed"] = sum(tot[k] for k in KEYS)
    return tot


def line(t: dict) -> str:
    if not t["responses"]:
        return "토큰: 세션 기록을 못 찾음"
    return (f"토큰(실측): 처리 {t['processed']:,} = 캐시읽기 {t['cache_read_input_tokens']:,} · "
            f"캐시쓰기 {t['cache_creation_input_tokens']:,} · 입력 {t['input_tokens']:,} · 출력 {t['output_tokens']:,}"
            f" · 응답 {t['responses']}회 · {','.join(t['models'])}")


if __name__ == "__main__":
    print(line(measure()))
