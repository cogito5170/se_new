"""POLICY.md 중 **기계로 볼 수 있는 것**을 최종 HTML 에서 검사한다.

    위반 = 검사(html)          # list[str], 비어 있으면 통과

Markdown 으로 쓴 보고서든 파이썬으로 지은 보고서든 결국 HTML 이 되므로 여기서 한 번에 본다.
글자만 보는 검사의 한계는 그대로다(CLAUDE.md: 글자를 보는 검사는 그 자리를 못 본다) --
절 이름이 있다고 내용이 옳은 것은 아니다. 이 검사는 **빠진 것**을 잡을 뿐이다.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

# (이름, 제목 안에 하나라도 있어야 하는 키워드)
필수절 = [
    ("요약", ("요약",)),
    ("단점·한계", ("단점", "한계")),
    ("선행연구", ("선행",)),
    ("원리·이론", ("원리", "이론")),
    ("설계·사양", ("설계", "사양")),
    ("결과", ("결과",)),
    ("실험·검증 청사진", ("실험", "검증")),
    ("증명한 것/못 한 것", ("증명", "하지 않은", "못 한", "못한")),
    ("참고문헌", ("참고문헌", "참고 문헌", "References")),
]
확인수준 = re.compile(r"\[(전문|초록|목록|조각|기억)\]")
과장 = re.compile(r"(세계\s*최초|획기적|혁신적|완벽한|완벽하게|revolutionary|breakthrough)", re.I)
얼버무림 = re.compile(r"\[verify\]", re.I)


class _P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.heads, self.refs, self.figs, self.text = [], [], [], []
        self.절 = {}                      # h2 제목 -> 그 절의 본문 (요약 검사가 다음 절까지 읽던 거짓 초록을 막는다)
        self._cur = None
        self._stack, self._buf, self._in_refs, self._fig = [], None, 0, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._stack.append(tag)
        if tag in ("h1", "h2", "h3"):
            self._buf = ["h", tag, ""]
        if tag == "ol" and "refs" in (a.get("class") or ""):
            self._in_refs += 1
        if tag == "li" and self._in_refs:
            self._buf = ["r", tag, ""]
        if tag == "figure":
            self._fig = {"img": False, "cap": ""}
        if tag == "img" and self._fig is not None:
            self._fig["img"] = True
        if tag == "figcaption" and self._fig is not None:
            self._buf = ["c", tag, ""]

    def handle_endtag(self, tag):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        if self._buf and self._buf[1] == tag:
            kind, _, txt = self._buf
            txt = " ".join(txt.split())
            if kind == "h":
                self.heads.append(txt)
                if tag in ("h1", "h2"):
                    self._cur = txt
                    self.절.setdefault(txt, "")
            elif kind == "r":
                self.refs.append(txt)
            elif kind == "c" and self._fig is not None:
                self._fig["cap"] = txt
            self._buf = None
        if tag == "ol" and self._in_refs:
            self._in_refs -= 1
        if tag == "figure" and self._fig is not None:
            self.figs.append(self._fig)
            self._fig = None

    def handle_data(self, data):
        if self._buf is not None:
            self._buf[2] += data
        if not (self._stack and self._stack[-1] in ("script", "style")):
            self.text.append(data)
            if self._cur is not None and not (self._buf and self._buf[0] == "h"):
                self.절[self._cur] += data


def 읽기(html: str) -> _P:
    p = _P()
    p.feed(html)
    return p


def 검사(html: str) -> "list[str]":
    p = 읽기(html)
    위반 = []
    제목 = " | ".join(p.heads)
    for 이름, 키 in 필수절:
        if not any(k in 제목 for k in 키):
            위반.append(f"필수 절 없음: {이름} (제목에 {' / '.join(키)} 중 하나)")
    if not p.refs:
        위반.append("참고문헌 목록이 없다 (<ol class='refs'> 또는 Markdown 의 '## 참고문헌' 아래 번호 목록)")
    for i, r in enumerate(p.refs, 1):
        if not 확인수준.search(r):
            위반.append(f"참고문헌 {i}: 확인 수준 표시 없음 ([전문]/[초록]/[목록]/[조각]/[기억]) -- {r[:60]}")
    for i, f in enumerate(p.figs, 1):
        if f["img"] and len(f["cap"].strip()) < 4:
            위반.append(f"그림 {i}: 캡션이 없다")
    본문 = " ".join(p.text)
    for m in 과장.finditer(본문):
        위반.append(f"과장 어휘: '{m.group(0)}' -- 깨지는 조건과 함께 수치로 말할 것")
    if 얼버무림.search(본문):
        위반.append("[verify] 표기 -- 확인 수준([조각] 등)으로 바꿀 것")
    # 요약 절 **본문만** 본다. 첫 판은 '요약' 뒤 3000자를 봐서 다음 절의 '모델' 에 걸려 통과했다 --
    # tests/test_reportkit.py 가 잡은 거짓 초록이다.
    요약 = " ".join(v for k, v in p.절.items() if "요약" in k)
    if any("요약" in k for k in p.절) and not re.search(r"(모델|실측|문헌|가정|시뮬레이션)", 요약):
        위반.append("요약에 수치의 출처(모델/실측/문헌/가정) 표시가 없다")
    return 위반


if __name__ == "__main__":
    import sys
    v = 검사(open(sys.argv[1], encoding="utf-8").read())
    print("\n".join(v) if v else "통과")
    raise SystemExit(1 if v else 0)
