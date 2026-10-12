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

# ── 원화 환산 ─────────────────────────────────────────────────────────────
# API 정가로 센 값이다. 구독(Pro/Max)으로 돌면 토큰마다 돈이 나가지 않고 한도에서 깎인다 --
# 그래서 이 수는 "API 로 돌렸다면 얼마인가" 다.
# 출처 https://platform.claude.com/docs/en/about-claude/pricing (2026-10-12 확인), 백만 토큰당 USD.
# 한 요청의 프롬프트(입력+캐시쓰기+캐시읽기)가 10만을 넘으면 그 요청 전체가 비싼 칸으로 간다.
PRICE = {
    "claude-haiku-5-5": {"lo": dict(inp=0.10, w5=0.125, w1=0.20, r=0.01, o=0.50),
                         "hi": dict(inp=0.50, w5=0.625, w1=1.00, r=0.05, o=2.50), "cut": 100_000},
    "claude-opus-5-5": {"lo": dict(inp=4.0, w5=5.0, w1=8.0, r=0.20, o=20.0), "cut": None},
}
SEARCH_USD = 0.01        # 웹 검색 한 번 (1,000회 10달러). WebFetch 는 따로 안 받는다
KRW_PER_USD = 1342       # open.er-api.com, 2026-10-11 00:02 UTC 기준 1,341.69


def cost_usd(usages: list[dict], model: str) -> tuple[float, int]:
    """(달러, 10만 넘은 요청 수). 값표에 없는 모델은 Haiku 값으로 센다."""
    pr = PRICE.get(model, PRICE["claude-haiku-5-5"])
    usd, big = 0.0, 0
    for u in usages:
        cc = u.get("cache_creation") or {}
        w1 = int(cc.get("ephemeral_1h_input_tokens") or 0)
        w5 = int(cc.get("ephemeral_5m_input_tokens") or 0) if cc else int(u.get("cache_creation_input_tokens") or 0)
        prompt = sum(int(u.get(k) or 0) for k in KEYS[:3])
        hi = pr.get("cut") and prompt > pr["cut"]
        big += bool(hi)
        t = pr["hi"] if hi else pr["lo"]
        usd += (int(u.get("input_tokens") or 0) * t["inp"] + w5 * t["w5"] + w1 * t["w1"]
                + int(u.get("cache_read_input_tokens") or 0) * t["r"] + int(u.get("output_tokens") or 0) * t["o"]) / 1e6
    return usd, big


def measure(root: Path | None = None) -> dict:
    root = root or Path.home() / ".claude" / "projects"
    seen: dict[str, dict] = {}
    models: set[str] = set()
    # 지금 이 회차의 기록 하나만 센다 -- 가장 최근에 쓰인 파일. 실측 2026-10-12: 하위 에이전트로
    # 돌렸더니 부모 세션의 기록까지 다 더해 2,100만이 찍혔다(제 몫은 360만).
    files = sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    for f in files[-1:]:
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
    model = sorted(models)[-1] if models else "claude-haiku-5-5"
    tot["token_usd"], tot["over_cut"] = cost_usd(list(seen.values()), model)
    return tot


def won(t: dict) -> int:
    return round((t.get("token_usd", 0.0) + t.get("web_search", 0) * SEARCH_USD) * KRW_PER_USD)


def line(t: dict) -> str:
    if not t["responses"]:
        return "토큰: 세션 기록을 못 찾음"
    return (f"토큰(실측): 처리 {t['processed']:,} = 캐시읽기 {t['cache_read_input_tokens']:,} · "
            f"캐시쓰기 {t['cache_creation_input_tokens']:,} · 입력 {t['input_tokens']:,} · 출력 {t['output_tokens']:,}"
            f" · 응답 {t['responses']}회 · {','.join(t['models'])}"
            f" · ≈ {won(t):,}원(API 정가, 검색 {t.get('web_search', 0)}회 포함, 10만 넘은 요청 {t.get('over_cut', 0)}회,"
            f" ${t.get('token_usd', 0.0):.3f}×{KRW_PER_USD})")


if __name__ == "__main__":
    print(line(measure()))
