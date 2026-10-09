"""**요청 파일 하나 -> dig 를 차례로 -> 받은 것 전부를 남긴다.**

에이전트 세션의 컨테이너는 나가는 길이 막혀 있다(실측 2026-10-09: `dig/run.py --망`
22개 문 중 21개가 프록시 403, 나머지 하나도 403). 그 자리에서 "못 돌린다" 로 끝내면
찾아 준 것이 없다. 그래서 **망이 열린 Actions 러너에 맡긴다** --
`.github/workflows/dig.yml` 이 `dig/requests/<이름>.json` 이 들어오면 이것을 돌리고
`dig/results/<이름>/` 를 같은 브랜치에 되밀어 준다.

요청 꼴:

    {"이름": "magazine2026",
     "url":  [{"주소": "https://...", "따라": 6}],
     "찾기": [{"물음": "...", "파": 4}],
     "pdf":  ["https://.../kit.pdf"]}

`dig/` 의 규율 그대로다 -- **고르지 않는다.** 받은 JSON 을 통째로 gzip 해 둔다.
못 받은 것도 까닭과 함께 `요약.json` 에 남긴다. 빈손과 '403 이라 못 받았다' 는 다른 말이다.

    python3 dig/batch.py dig/requests/magazine2026.json
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
한도초 = 300
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _이름(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def _dig(argv: list) -> tuple:
    """dig/run.py 를 돌려 (끝값, stdout, stderr 끝) 을 낸다. 시간이 넘으면 끝값 124."""
    try:
        p = subprocess.run([sys.executable, str(REPO / "dig" / "run.py"), *argv, "--json"],
                           capture_output=True, text=True, timeout=한도초, cwd=REPO)
        return p.returncode, p.stdout, p.stderr[-400:]
    except subprocess.TimeoutExpired as e:
        # text=True 여도 시간이 넘으면 bytes 로 올 때가 있다.
        out = e.stdout or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        return 124, out, "시간 넘음"


def _pdf(url: str, 틈: float) -> tuple:
    """pdf 는 dig 의 뽑개가 글자로 못 푼다(run.py 가 일부러 뺀다). pdftotext 로 푼다."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=틈) as r:
            몸통 = r.read()
    except Exception as e:                                           # noqa: BLE001
        return 3, "", f"못 받음: {e}"
    try:
        p = subprocess.run(["pdftotext", "-layout", "-", "-"], input=몸통,
                           capture_output=True, timeout=120)
        return (0 if p.stdout.strip() else 3), p.stdout.decode("utf-8", "replace"), \
            p.stderr.decode("utf-8", "replace")[-400:]
    except FileNotFoundError:
        return 3, "", "pdftotext 없음 (poppler-utils)"


def 돌리기(요청: dict, 낼곳: Path, 틈: float = 20.0) -> list:
    낼곳.mkdir(parents=True, exist_ok=True)
    요약 = []

    def 남기기(갈래: str, 무엇: str, 끝값: int, 몸: str, 꼬리: str, 걸린: float, 꼴: str):
        파일 = f"{갈래}-{_이름(무엇)}.{꼴}.gz"
        with gzip.open(낼곳 / 파일, "wt", encoding="utf-8") as f:
            f.write(몸)
        줄 = {"갈래": 갈래, "무엇": 무엇, "끝값": 끝값, "바이트": len(몸.encode("utf-8")),
             "초": round(걸린, 1), "파일": 파일, "꼬리": 꼬리.strip()[-200:]}
        if 꼴 == "json":
            try:
                d = json.loads(몸)
                줄["쪽"] = len(d.get("쪽") or [])
                줄["찾은주소"] = len(d.get("찾은주소") or [])
                줄["받은곳"] = [(x.get("url"), x.get("코드"), x.get("왜")) for x in
                             (d.get("받은곳") or d.get("두드린문") or [])][:30]
            except ValueError:
                줄["쪽"] = 0
        요약.append(줄)
        print(f"[{갈래}] {끝값} {줄['바이트']:>8}B {걸린:5.1f}s {무엇[:90]}", flush=True)

    for x in 요청.get("url", []):
        t = time.time()
        k, out, err = _dig(["--url", x["주소"], "--따라", str(x.get("따라", 6)),
                            "--틈", str(틈)] + (["--찾", x["찾"]] if x.get("찾") else []))
        남기기("url", x["주소"], k, out, err, time.time() - t, "json")
    for x in 요청.get("찾기", []):
        t = time.time()
        k, out, err = _dig(["--찾기", x["물음"], "--파", str(x.get("파", 4)),
                            "--따라", str(x.get("따라", 4)), "--틈", str(틈)])
        남기기("찾기", x["물음"], k, out, err, time.time() - t, "json")
    for u in 요청.get("pdf", []):
        t = time.time()
        k, out, err = _pdf(u, 틈 * 3)
        남기기("pdf", u, k, out, err, time.time() - t, "txt")

    (낼곳 / "요약.json").write_text(json.dumps(
        {"요청": 요청.get("이름"), "때": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         "줄": 요약}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 요약


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="요청 파일대로 dig 를 차례로 돌린다")
    ap.add_argument("요청")
    ap.add_argument("--낼곳", default="")
    ap.add_argument("--틈", type=float, default=20.0)
    a = ap.parse_args(argv)
    요청 = json.loads(Path(a.요청).read_text(encoding="utf-8"))
    낼곳 = Path(a.낼곳) if a.낼곳 else REPO / "dig" / "results" / 요청["이름"]
    요약 = 돌리기(요청, 낼곳, a.틈)
    받은 = sum(1 for z in 요약 if z["끝값"] == 0)
    print(f"\n{len(요약)} 중 {받은} 받음 -> {낼곳}")
    return 0 if 받은 else 3


if __name__ == "__main__":
    raise SystemExit(main())
