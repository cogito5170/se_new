"""POLICY.md 를 따르는 기술 보고서: HTML 조각 -> 한 HTML -> PDF (headless Chromium).

두 가지로 쓴다.
  1) 파이썬에서 조각을 짓는다:   kit.eq(tex) · kit.fig(path, cap) · kit.table(rows, head) · kit.drawing(path, cap)
                                 kit.page(body_html, title) -> html ;  kit.pdf(html, out_pdf)
  2) Markdown 한 파일:            build_md("보고서.md", "out.pdf")
     - 수식  $$…$$ (가운데) · $…$ (줄 안)          -> KaTeX (저장소 동봉, 인터넷 불필요)
     - 그림  ![캡션](경로)                          -> 번호 붙은 <figure>
     - 도면  !drawing[캡션](경로)  (한 줄)          -> 가로 A4 한 쪽
     - 새 쪽  <!-- pagebreak -->
     - 참고문헌은 '## 참고문헌' 아래 번호 목록, 항목마다 [조각] 같은 확인 수준

**정책 검사(check.검사)를 통과해야 PDF 를 만든다.** strict=False 면 만들되 위반을 첫 쪽에 찍는다.
"""
from __future__ import annotations

import html as _html
import os
import re
from pathlib import Path

from reportkit import check

HERE = Path(__file__).resolve().parent
KATEX = HERE / "vendor" / "katex"

_n = {"fig": 0}


def reset():
    _n["fig"] = 0


def eq(tex: str, display: bool = True) -> str:
    t = _html.escape(tex, quote=True)
    return f'<span class="tex" data-display="{1 if display else 0}">{t}</span>' if not display else f'<div class="tex" data-display="1">{t}</div>'


def fig(path, cap: str, width: str = "90%", num: bool = True) -> str:
    p = Path(path)
    if not p.exists():
        return f"<p class='miss'>[그림 없음: {_html.escape(p.name)}]</p>"
    if num:
        _n["fig"] += 1
        cap = f"<b>그림 {_n['fig']}.</b> {cap}"
    return f"<figure><img src='{p.resolve().as_uri()}' style='width:{width}'><figcaption>{cap}</figcaption></figure>"


def drawing(path, cap: str) -> str:
    return "<section class='land'>" + fig(path, cap, "100%") + "</section>"


def table(rows, head=None, cls: str = "") -> str:
    h = f"<table class='{cls}'>"
    if head:
        h += "<tr>" + "".join(f"<th>{c}</th>" for c in head) + "</tr>"
    for r in rows:
        h += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
    return h + "</table>"


def refs(items) -> str:
    return "<ol class='refs'>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>"


CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
@page land { size: A4 landscape; margin: 8mm; }
body{font-family:"NanumGothic","NanumSquare","Noto Sans CJK KR",sans-serif;color:#1b2129;font-size:10.2pt;line-height:1.62;margin:0}
section{break-before:page}
section.land{page:land} section.land figure{margin:0} section.land img{max-height:165mm;object-fit:contain}
.cover{break-before:auto;padding-top:40mm}
.cover h1{font-family:"NanumSquare","NanumGothic";font-size:40pt;margin:6mm 0 2mm}
.cover h2{font-size:16pt;font-weight:700;line-height:1.4;margin:0 0 12mm;border:0}
.cv-top{font-size:9pt;letter-spacing:.12em;color:#5a6472}
.cv-box{border-left:4px solid #2a78d6;padding:4mm 6mm;background:#f2f6fb;display:flex;flex-direction:column;gap:2mm}
.cv-warn,.violations{margin-top:10mm;border:1.5px solid #c73535;color:#8a1f1f;padding:4mm 6mm;border-radius:2mm;font-size:9.5pt}
h1{font-size:18pt} h2,h2.h{font-family:"NanumSquare","NanumGothic";font-size:16pt;border-bottom:2px solid #1b2129;padding-bottom:1.5mm;margin:0 0 4mm}
h3{font-size:11.5pt;margin:5mm 0 2mm;color:#123d73}
table{border-collapse:collapse;width:100%;margin:2mm 0 4mm;font-size:9.2pt;break-inside:avoid}
th,td{border-bottom:.6px solid #c9d0d8;padding:1.3mm 2mm;text-align:left;vertical-align:top}
th{background:#eef2f6;font-weight:700}
table.small{font-size:8.4pt}
figure{margin:3mm 0;text-align:center;break-inside:avoid}
figure img{max-width:100%}
figcaption{font-size:8.8pt;color:#48525e;text-align:left;margin-top:1mm}
.two{display:grid;grid-template-columns:1fr 1fr;gap:4mm}
.eqbox{background:#f6f8fa;border:1px solid #dde3ea;border-radius:2mm;padding:1mm 5mm;margin:2mm 0 4mm}
.eqlab{font-size:8.6pt;color:#5a6472;margin-top:2mm}
div.tex{margin:1.5mm 0;text-align:center}
.small{font-size:8.8pt;color:#48525e}
ol,ul{padding-left:6mm} li{margin:1mm 0}
pre{background:#f3f5f7;padding:3mm;font-size:8.2pt;border-radius:2mm;white-space:pre-wrap}
.refs li{font-size:8.6pt}
.miss{color:#c73535}
"""


def page(body: str, title: str, violations: "list[str] | None" = None) -> str:
    css = (KATEX / "katex.min.css").read_text(encoding="utf-8").replace("url(fonts/", f"url({(KATEX / 'fonts').as_uri()}/")
    warn = ""
    if violations:
        warn = "<div class='violations'><b>정책 위반 (strict=False 로 강행)</b><ul>" + "".join(f"<li>{_html.escape(v)}</li>" for v in violations) + "</ul></div>"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{_html.escape(title)}</title>
<style>{css}{CSS}</style><script src="{(KATEX / 'katex.min.js').as_uri()}"></script></head><body>{warn}{body}
<script>
(function(){{var bad=0;document.querySelectorAll('.tex').forEach(function(el){{try{{katex.render(el.textContent,el,{{displayMode:el.dataset.display==='1',throwOnError:true}});}}catch(e){{bad++;el.style.color='#c00';el.textContent='MATH ERROR: '+e.message;}}}});window.__mathErrors=bad;window.__katexDone=true;}})();
</script></body></html>"""


def pdf(html: str, out_pdf, footer: str = "") -> dict:
    """HTML 문자열 -> PDF. 수식 오류 수와 쪽 수를 돌려준다. Chromium 이 없으면 그렇다고 말한다."""
    from playwright.sync_api import sync_playwright
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    src = out_pdf.with_suffix(".html")
    src.write_text(html, encoding="utf-8")
    exe = _chromium()
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        pg = b.new_page()
        pg.goto(src.resolve().as_uri(), wait_until="load", timeout=180000)
        pg.wait_for_function("window.__katexDone===true", timeout=60000)
        errs = pg.evaluate("window.__mathErrors")
        pg.pdf(path=str(out_pdf), prefer_css_page_size=True, print_background=True, display_header_footer=True,
               header_template="<div></div>",
               footer_template=("<div style='width:100%;font-size:8px;color:#777;text-align:center;font-family:NanumGothic'>"
                                f"{_html.escape(footer)} — <span class='pageNumber'></span>/<span class='totalPages'></span></div>"),
               margin={"top": "14mm", "bottom": "14mm", "left": "14mm", "right": "14mm"})
        b.close()
    # 쪽 수는 부가 정보다. pypdf 는 어떤 환경에서 import 만으로 패닉(BaseException)을 낸다 -- 바이트로 센다.
    n = len(re.findall(rb"/Type\s*/Page(?![s\w])", out_pdf.read_bytes()))
    return {"pdf": str(out_pdf), "html": str(src), "math_errors": errs, "pages": n, "bytes": out_pdf.stat().st_size}


def _chromium():
    p = os.environ.get("SE_CHROMIUM")
    if p and os.path.exists(p):
        return p
    import glob
    for c in sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"), reverse=True):
        return c
    return None


# ------------------------------------------------------------------ Markdown
_MATH = re.compile(r"\$\$(.+?)\$\$|(?<![\\$])\$(?!\s)([^$\n]+?)(?<!\s)\$", re.S)


def md_to_html(md_text: str, base: Path) -> str:
    import markdown
    reset()
    keep = []

    def hold(m):
        tex, disp = (m.group(1), True) if m.group(1) is not None else (m.group(2), False)
        keep.append(eq(tex.strip(), disp))
        return f"@@K{len(keep) - 1}@@"

    t = _MATH.sub(hold, md_text)
    blocks = []

    repo = HERE.parent.resolve()

    def img_path(p):
        q = Path(p)
        q = (q if q.is_absolute() else (base / q)).resolve()
        # 저장소 밖 파일을 PDF 에 싣지 않는다 (도구 인자는 LLM 이 만든 글이다 -- G014 와 같은 부류)
        return q if (q == repo or repo in q.parents) else Path("/nonexistent-outside-repo") / q.name

    def dwg(m):
        blocks.append(drawing(img_path(m.group(2)), m.group(1)))
        return f"\n\n@@B{len(blocks) - 1}@@\n\n"

    def pic(m):
        blocks.append(fig(img_path(m.group(2)), m.group(1)))
        return f"\n\n@@B{len(blocks) - 1}@@\n\n"

    t = re.sub(r"^!drawing\[(.*?)\]\((.*?)\)\s*$", dwg, t, flags=re.M)
    t = re.sub(r"^!\[(.*?)\]\((.*?)\)\s*$", pic, t, flags=re.M)
    h = markdown.markdown(t, extensions=["tables", "fenced_code", "sane_lists"])
    # 참고문헌 절 아래 첫 <ol> 에 refs 클래스
    h = re.sub(r"(<h2>[^<]*참고\s*문헌[^<]*</h2>\s*)<ol>", r"\1<ol class='refs'>", h)
    # h2 마다 새 쪽 (첫 h1/표지는 그대로)
    h = h.replace("<h2>", "</section><section><h2>")
    h = "<section class='cover'>" + h + "</section>"
    h = h.replace("<!-- pagebreak -->", "</section><section>")
    for i, b in enumerate(blocks):
        h = h.replace(f"<p>@@B{i}@@</p>", "</section>" + b + "<section>" if b.startswith("<section class='land'>") else b)
        h = h.replace(f"@@B{i}@@", b)
    for i, k in enumerate(keep):
        h = h.replace(f"@@K{i}@@", k)
    h = h.replace("\\$", "$")
    return h.replace("<section></section>", "")


def build_md(md_path, out_pdf, strict: bool = True, title: str = "") -> dict:
    md_path = Path(md_path)
    body = md_to_html(md_path.read_text(encoding="utf-8"), md_path.parent)
    return build_html(body, out_pdf, title or md_path.stem, strict=strict)


def build_html(body: str, out_pdf, title: str, strict: bool = True, footer: str = "") -> dict:
    v = check.검사(body)
    if v and strict:
        return {"ok": False, "violations": v, "pdf": None}
    r = pdf(page(body, title, v if v else None), out_pdf, footer or title)
    r.update(ok=r["math_errors"] == 0, violations=v)
    return r
