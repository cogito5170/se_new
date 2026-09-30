"""보고서 구성 정책(reportkit/POLICY.md)이 **실제로 막는지** 본다 -- 옳은 틀을 망가뜨려 매번 빨개지는가.

tests/test_논문원장_게이트.py 와 같은 방식이다: 글자만 보는 검사가 거짓 초록을 내던 자리라서,
옳게 채운 틀(template.md) 하나를 두고 규칙마다 하나씩 부순다.
실행: python3 tests/test_reportkit.py
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

뿌리 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(뿌리))

from reportkit import check, kit  # noqa: E402

FAIL = []


def ok(c, what):
    print(("  통과  " if c else "  실패  ") + what)
    if not c:
        FAIL.append(what)


틀 = (뿌리 / "reportkit/template.md").read_text(encoding="utf-8")


def 검(md):
    return check.검사(kit.md_to_html(md, 뿌리))


print("== 옳은 틀은 통과 ==")
ok(검(틀) == [], "template.md 통과")

print("\n== 필수 절을 하나씩 뺀다 ==")
for 제목줄, 기대 in (("## A. 단점과 한계", "단점"), ("## 1. 선행연구와 위치", "선행"), ("## 2. 원리와 이론", "원리"),
                   ("## 3. 설계와 사양", "설계"), ("## 4. 결과", "결과"), ("## 5. 실험·검증 청사진", "실험"),
                   ("## 7. 증명한 것과 못 한 것", "증명"), ("## 참고문헌", "참고문헌")):
    v = 검(틀.replace(제목줄, "## 기타"))
    ok(any(기대 in x for x in v), f"'{제목줄}' 없음 -> 위반")

print("\n== 근거·어휘 ==")
ok(any("확인 수준" in x for x in 검(틀.replace("[조각]", ""))), "확인 수준 없는 참고문헌 -> 위반")
ok(any("verify" in x for x in 검(틀 + "\n\n값은 3.2 [verify]\n")), "[verify] -> 위반")
ok(any("과장" in x for x in 검(틀.replace("이 작업이 찾은 것", "세계 최초로 찾은 것"))), "과장 어휘 -> 위반")
ok(any("출처" in x for x in 검(re.sub(r"(?s)## 요약.*?## A\.", "## 요약\n\n| 항목 | 값 |\n|---|---|\n| 용량 | 1.0 Ah |\n\n## A.", 틀))), "요약에 수치 출처 없음 -> 위반")

print("\n== 변환 ==")
h = kit.md_to_html("## 요약\n\n$$E=mc^2$$ 와 $a_b$ 그리고 \\$3.55\n", 뿌리)
ok(h.count('class="tex"') == 2 and "$3.55" in h and "3.55</span>" not in h, "수식 두 개, 이스케이프한 금액은 수식이 아니다")
h = kit.md_to_html("## 결과\n\n![밖](/etc/hostname)\n", 뿌리)
ok("그림 없음" in h, "저장소 밖 그림은 싣지 않는다")
png = next(iter(sorted((뿌리 / "render3d").rglob("*.png"))), None) or next(iter(sorted(뿌리.rglob("*.png"))), None)
if png:
    h = kit.md_to_html(f"## 결과\n\n![무엇을 보라]({png.relative_to(뿌리)})\n\n!drawing[도면]({png.relative_to(뿌리)})\n", 뿌리)
    ok("그림 1." in h and "그림 2." in h and "section class='land'" in h, "그림 번호 · 가로 도면 쪽")

print("\n== PDF (Chromium 이 있으면) ==")
try:
    import playwright.sync_api  # noqa: F401
    have = kit._chromium() is not None or Path.home().joinpath(".cache/ms-playwright").exists()
except ImportError:
    have = False
if have:
    with tempfile.TemporaryDirectory() as d:
        r = kit.build_html(kit.md_to_html(틀, 뿌리), Path(d) / "t.pdf", "틀")
        ok(r["ok"] and r["math_errors"] == 0 and r["pages"] >= 8, f"PDF {r['pages']}쪽 · 수식 오류 {r['math_errors']}")
        r = kit.build_html(kit.md_to_html(틀.replace("## A. 단점과 한계", "## 기타"), 뿌리), Path(d) / "x.pdf", "x")
        ok(r["pdf"] is None and r["violations"], "정책 위반이면 PDF 를 안 만든다")
else:
    print("  건너뜀  Chromium 이 없다 -- PDF 인쇄는 이 기계에서 못 봤다")

print(f"\n{'실패 ' + str(len(FAIL)) if FAIL else '전부 통과'}")
sys.exit(1 if FAIL else 0)
