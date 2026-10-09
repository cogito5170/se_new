#!/usr/bin/env python3
"""Build the magazine reference catalogue: one card per real magazine image, with four components
(layout / typography / image / colour) on every card.

    python3 magazine_catalog.py --images magazine_pd/images --out catalog_public --public-only
    python3 magazine_catalog.py --images inbox --out catalog_local

Inputs
  --images DIR          real images (repeatable). If DIR/../manifests/collection_manifest.jsonl exists
                        (a Met collection), its title / date / rights are used.
  --annotations FILE    catalog/annotations.json: layout, typography and image tags per file, chosen
                        from catalog_vocab.py. Colour is measured from the pixels, not annotated.
Output
  OUT/index.html and OUT/images/*.jpg (web-size copies). Originals are never changed.
  --public-only keeps only public-domain records, so OUT can be published.

Python 3.9+, Pillow.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

from PIL import Image

import catalog_measure
import catalog_vocab as V

PROJECT = Path(__file__).resolve().parent
DEFAULT_ANNOTATIONS = PROJECT / "catalog" / "annotations.json"
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
WEB_SIZE = 1400


def load_annotations(path: Path) -> "dict[str, dict]":
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out, errors = {}, []
    for i, a in enumerate(data):
        name = a.get("file")
        if not name:
            errors.append(f"entry {i}: no file")
            continue
        for comp in V.COMPONENTS:
            bad = V.unknown_tags(comp, a.get(comp, []))
            if bad:
                errors.append(f"{name}: {comp} has terms not in catalog_vocab.py: {bad}")
        if a.get("rights") and a["rights"] not in V.RIGHTS:
            errors.append(f"{name}: unknown rights {a['rights']!r}")
        out[name] = a
    if errors:
        raise SystemExit("annotation errors:\n  " + "\n  ".join(errors))
    return out


def met_records(images_dir: Path) -> "dict[str, dict]":
    m = images_dir.parent / "manifests" / "collection_manifest.jsonl"
    recs = {}
    if m.exists():
        for line in m.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                recs[Path(r["local_file_path"]).name] = r
    return recs


def web_copy(src: Path, out_dir: Path) -> "tuple[str, int, int]":
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{src.stem}.jpg"
    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        im.thumbnail((WEB_SIZE, WEB_SIZE))
        im.save(out_dir / name, "JPEG", quality=84, optimize=True, progressive=True)
    return name, w, h


def collect(image_dirs, annotations, public_only):
    refs, skipped = [], []
    for d in image_dirs:
        met = met_records(d)
        for p in sorted(d.iterdir()):
            if p.suffix.lower() not in EXTS or p.name.startswith("."):
                continue
            a = dict(annotations.get(p.name, {}))
            m = met.get(p.name)
            if m:  # official metadata wins for provenance; annotation supplies the analysis
                a.setdefault("magazine", m.get("title"))
                a.setdefault("issue", m.get("creation_date_text"))
                a.setdefault("creator", m.get("creator"))
                a.setdefault("source_url", m.get("source_record_url"))
                a["rights"] = "public_domain_cc0" if m.get("is_public_domain") is True else a.get("rights")
                a.setdefault("credit", m.get("attribution_text"))
            rights = a.get("rights") or "third_party_unverified"
            if public_only and rights not in V.PUBLIC_RIGHTS:
                skipped.append((p.name, rights))
                continue
            a["rights"] = rights
            a["path"] = p
            a["complete"] = all(a.get(c) for c in ("layout", "typography", "image"))
            refs.append(a)
    return refs, skipped


def tag_html(comp, t):
    e = html.escape
    en = V.ENGLISH.get(t, "")
    return (f'<button type="button" class="tag" data-tag="{e(comp)}:{e(t)}" title="{e(en)}">{e(t)}'
            f'<span>{e(en)}</span></button>')


def build(image_dirs, annotations_path, out_dir: Path, public_only: bool) -> dict:
    annotations = load_annotations(annotations_path)
    refs, skipped = collect(image_dirs, annotations, public_only)
    e = html.escape
    cards, waiting = [], []
    for a in refs:
        web, w, h = web_copy(a["path"], out_dir / "images")
        col = catalog_measure.measure(a["path"])
        swatches = "".join(f'<span class="sw" style="background:{c["hex"]}" title="{c["hex"]} · {round(c["share"] * 100)}%"></span>'
                           for c in col["palette"])
        hexes = " ".join(c["hex"] for c in col["palette"])
        measured = [col["scheme"], col["key"], col["contrast"], col["chroma"]]
        rows = []
        for comp in ("layout", "typography", "image"):
            tags = "".join(tag_html(comp, t) for t in a.get(comp, [])) or '<span class="pending">분석 대기</span>'
            rows.append(f'<div class="row"><dt>{e(V.COMPONENT_LABEL[comp])}</dt><dd>{tags}</dd></div>')
        colour_tags = "".join(tag_html("colour", t) for t in measured + a.get("colour_tags", []))
        rows.append(f'<div class="row"><dt>색상</dt><dd><div class="sws">{swatches}</div>'
                    f'<p class="hex">{e(hexes)}</p>{colour_tags}</dd></div>')
        all_tags = [f"{c}:{t}" for c in ("layout", "typography", "image") for t in a.get(c, [])] + \
                   [f"colour:{t}" for t in measured + a.get("colour_tags", [])]
        title = a.get("magazine") or a["path"].stem
        sub = " · ".join(x for x in (a.get("issue"), a.get("page_type"), a.get("creator")) if x)
        src = f'<a href="{e(a["source_url"])}" target="_blank" rel="noopener">출처</a>' if a.get("source_url") else ""
        card = (f'<article class="ref" data-tags="{e("|".join(all_tags))}">'
                f'<a class="photo" href="images/{e(web)}" target="_blank" rel="noopener">'
                f'<img src="images/{e(web)}" alt="{e(title)}" loading="lazy" width="{w}" height="{h}"></a>'
                f'<header><h3>{e(title)}</h3><p class="sub">{e(sub)}</p></header>'
                f'<dl>{"".join(rows)}</dl>'
                f'<p class="foot">{e(V.RIGHTS[a["rights"]])} {src}'
                f'{"<br>" + e(a["credit"]) if a.get("credit") else ""}'
                f'{"<br>분석: " + e(a.get("annotated_by", "")) if a.get("annotated_by") else ""}</p></article>')
        (cards if a["complete"] else waiting).append(card)
    page = render(cards, waiting, public_only)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    return {"complete": len(cards), "waiting": len(waiting), "skipped_not_public": skipped,
            "out": str(out_dir / "index.html")}


def render(cards, waiting, public_only) -> str:
    total = len(cards) + len(waiting)
    note = ("퍼블릭 도메인 자료만 담은 공개판입니다." if public_only else
            "개인 참고용 로컬판입니다. 저작권이 있는 지면이 들어 있으니 공유하지 마세요.")
    wait_block = (f'<section><h2>분석 대기 <span>{len(waiting)}</span></h2><p class="dek">사진과 색상 측정만 있고 '
                  f'레이아웃·타이포·이미지 분석이 아직 없는 레퍼런스입니다.</p><div class="grid">{"".join(waiting)}</div></section>'
                  if waiting else "")
    return f"""<title>매거진 레퍼런스 카탈로그</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: black-and-white magazine catalogue. Each reference: real image first, then four component rows
   (layout / typography / image / colour). Selecting tags keeps only references that carry all of them. */
:root{{--paper:#ffffff;--ink:#000000;--muted:#5c5c5c;--soft:#e6e6e6;
  --sans:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--paper:#000000;--ink:#ffffff;--muted:#a3a3a3;--soft:#262626;color-scheme:dark}}}}
:root[data-theme="dark"]{{--paper:#000000;--ink:#ffffff;--muted:#a3a3a3;--soft:#262626;color-scheme:dark}}
[hidden]{{display:none!important}}
body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 var(--sans);padding:0 16px;padding-block:24px 56px}}
.wrap{{max-width:1240px;margin:0 auto;display:grid;gap:28px}}
.mast{{border-bottom:3px solid var(--ink);padding-bottom:18px;display:grid;gap:8px}}
.kicker{{font:500 12px var(--mono);letter-spacing:.06em;color:var(--muted);margin:0}}
h1{{font:700 clamp(34px,7vw,76px)/1 var(--sans);letter-spacing:-.03em;margin:0;text-wrap:balance}}
.dek{{color:var(--muted);max-width:68ch;margin:0}}
.bar{{position:sticky;top:env(safe-area-inset-top,0px);background:var(--paper);z-index:2;padding-block:10px;
  border-bottom:1px solid var(--soft);display:flex;flex-wrap:wrap;gap:8px;align-items:center}}
.bar .now{{font:500 12px var(--mono);color:var(--muted)}} .bar button{{font:inherit;font-size:13px;background:none;
  border:1.5px solid var(--ink);color:var(--ink);padding:4px 10px;cursor:pointer}}
h2{{font:700 22px var(--sans);margin:0 0 14px;border-top:1px solid var(--ink);padding-top:10px}} h2 span{{font:400 12px var(--mono);color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:36px 24px}}
.ref{{display:grid;gap:12px;align-content:start;min-width:0}}
.photo{{display:block;border:1px solid var(--ink);background:var(--soft);line-height:0}}
.photo img{{width:100%;height:auto;display:block}}
.ref h3{{font:700 18px/1.25 var(--sans);margin:0}} .sub{{margin:2px 0 0;font:400 12px var(--mono);color:var(--muted)}}
dl{{margin:0;display:grid;border-top:1px solid var(--ink)}}
.row{{display:grid;grid-template-columns:84px 1fr;gap:10px;padding:8px 0;border-bottom:1px solid var(--soft)}}
dt{{font:500 11px var(--mono);letter-spacing:.04em;color:var(--muted);padding-top:3px}}
dd{{margin:0;display:flex;flex-wrap:wrap;gap:4px;min-width:0}}
.tag{{font:inherit;font-size:12px;border:1px solid var(--ink);background:var(--paper);color:var(--ink);padding:1px 6px;cursor:pointer}}
.tag span{{display:none}} .tag[aria-pressed="true"]{{background:var(--ink);color:var(--paper)}}
.sws{{display:flex;width:100%;height:22px;border:1px solid var(--ink)}} .sw{{flex:1}}
.hex{{width:100%;margin:2px 0;font:400 11px var(--mono);color:var(--muted);overflow-wrap:anywhere}}
.pending{{font-size:12px;color:var(--muted)}} .foot{{margin:0;font-size:12px;color:var(--muted)}} a{{color:var(--ink)}}
.empty{{color:var(--muted)}}
@media (max-width:420px){{.grid{{grid-template-columns:1fr}}}}
</style>
<div class="wrap">
<header class="mast">
  <p class="kicker">MAGAZINE REFERENCE CATALOGUE · {total} REFERENCES</p>
  <h1>매거진 레퍼런스 카탈로그</h1>
  <p class="dek">레퍼런스 하나마다 레이아웃·타이포그래피·이미지·색상 네 요소를 함께 기록했습니다. 태그를 누르면 그 태그를 모두 가진
  레퍼런스만 남습니다. 색상은 사진의 픽셀에서 측정한 값이고, 나머지 세 요소는 사진을 보고 전문용어 사전에서 골라 붙였습니다. {note}</p>
</header>
<div class="bar"><span class="now" id="now">선택한 태그 없음</span><button type="button" id="clear" hidden>선택 해제</button></div>
<section><h2>레퍼런스 <span>{len(cards)}</span></h2><div class="grid">{"".join(cards) or '<p class="empty">분석이 끝난 레퍼런스가 아직 없습니다.</p>'}</div></section>
{wait_block}
<p class="empty" id="none" hidden>선택한 태그를 모두 가진 레퍼런스가 없습니다.</p>
</div>
<script>
(function(){{
var active=new Set(),now=document.getElementById('now'),clear=document.getElementById('clear'),none=document.getElementById('none');
function apply(){{var shown=0;
  document.querySelectorAll('.ref').forEach(function(r){{var tags=r.dataset.tags.split('|'),ok=true;
    active.forEach(function(t){{if(tags.indexOf(t)<0)ok=false;}});r.hidden=!ok;if(ok)shown++;}});
  document.querySelectorAll('.tag').forEach(function(b){{b.setAttribute('aria-pressed',active.has(b.dataset.tag)?'true':'false');}});
  now.textContent=active.size?Array.from(active).map(function(t){{return t.split(':')[1];}}).join(' ∩ ')+' · '+shown+'건':'선택한 태그 없음';
  clear.hidden=!active.size;none.hidden=shown>0;}}
document.addEventListener('click',function(ev){{var b=ev.target.closest('.tag');if(!b)return;
  var t=b.dataset.tag;if(active.has(t))active.delete(t);else active.add(t);apply();}});
clear.addEventListener('click',function(){{active.clear();apply();}});apply();
}})();
</script>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--images", type=Path, action="append", required=True)
    ap.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--public-only", action="store_true")
    a = ap.parse_args(argv)
    r = build(a.images, a.annotations, a.out, a.public_only)
    print(f"complete {r['complete']} · waiting for analysis {r['waiting']} · not public (left out) "
          f"{len(r['skipped_not_public'])} -> {r['out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
