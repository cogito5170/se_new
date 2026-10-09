#!/usr/bin/env python3
"""Magazine URL catalogue: one card per magazine, with its official URL, a representative image and
four component link sets (layout / typography / image / colour).

    python3 magazine_urls.py fetch    # Mac: fetch each site's own preview image (og:image), 1 request/s
    python3 magazine_urls.py build    # write magazine_urls.html (images embedded if fetched)

The representative image is the preview image each magazine declares for link sharing (og:image /
twitter:image) on its official homepage. It is the publisher's image: keep the built file for personal
reference and do not republish it. robots.txt is honoured; nothing else on the sites is fetched.
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote_plus

PROJECT = Path(__file__).resolve().parent
CACHE = PROJECT / "magazine_urls"
UA = "magazine-url-catalogue/0.1 (personal reference; one preview image per site)"
INTERVAL = 1.0
MAX_HTML = 3 * 1024 * 1024
MAX_IMAGE = 12 * 1024 * 1024

# (slug, 잡지명, 국가, 성격, 공식 URL 또는 None, 메모)
# URLs were checked against Wikipedia infoboxes / publisher pages on 2026-10-09; notes record what is uncertain.
MAGAZINES = [
    # 글로벌 패션
    ("vogue", "Vogue", "미국", "글로벌 패션", "https://www.vogue.com", ""),
    ("harpers-bazaar", "Harper's Bazaar", "미국", "글로벌 패션", "https://www.harpersbazaar.com", ""),
    ("elle", "Elle", "미국", "글로벌 패션", "https://www.elle.com", ""),
    ("w-magazine", "W Magazine", "미국", "글로벌 패션", "https://www.wmagazine.com", ""),
    ("interview", "Interview", "미국", "패션·컬처", "https://www.interviewmagazine.com", ""),
    ("numero", "Numéro", "프랑스", "글로벌 패션", "https://www.numero.com", ""),
    ("cr-fashion-book", "CR Fashion Book", "미국", "패션", "https://www.crfashionbook.com", "카린 로이트펠드 편집, 연 2회"),
    # 인디펜던트 패션·컬처
    ("i-d", "i-D", "영국", "패션·컬처", "https://i-d.co", "2025년 봄부터 연 2회로 재발행"),
    ("dazed", "Dazed", "영국", "패션·컬처", "https://www.dazeddigital.com", ""),
    ("another", "AnOther", "영국", "패션·컬처", "https://www.anothermag.com", ""),
    ("the-face", "The Face", "영국", "패션·컬처", "https://theface.com", "2026년 매각 후 발행 중단 보도. 사이트 상태 확인 필요"),
    ("love", "LOVE", "영국·프랑스", "패션", "https://lovemagazine.co", "2025년 새 플랫폼으로 재출범"),
    ("pop", "POP", "영국", "패션", "https://www.thepop.com", ""),
    ("purple", "Purple", "프랑스", "패션·아트", "https://purple.fr", ""),
    ("system", "System", "영국", "패션 저널", "https://system-magazine.com", ""),
    ("032c", "032c", "독일", "패션·컬처", "https://032c.com", ""),
    ("re-edition", "Re-Edition", "영국", "패션·컬처", "https://www.re-editionmagazine.com", ""),
    ("fantastic-man", "Fantastic Man", "네덜란드", "남성 패션", "https://www.fantasticman.com", ""),
    ("the-gentlewoman", "The Gentlewoman", "영국", "여성 패션·컬처", "https://thegentlewoman.co.uk", "주소는 간접 출처로 확인"),
    ("document-journal", "Document Journal", "미국", "패션·아트", "https://www.documentjournal.com", "2025년 마지막 호로 종간된 것으로 보임"),
    ("self-service", "Self Service", "프랑스", "패션", None, "공식 사이트를 찾지 못함"),
    # 라이프스타일·인테리어
    ("kinfolk", "Kinfolk", "미국·덴마크", "라이프스타일", "https://www.kinfolk.com", ""),
    ("apartamento", "Apartamento", "스페인", "인테리어·라이프스타일", "https://www.apartamentomagazine.com", ""),
    # 한국판
    ("vogue-korea", "Vogue Korea", "한국", "한국판 패션", "https://www.vogue.co.kr", ""),
    ("w-korea", "W Korea", "한국", "한국판 패션", "https://www.wkorea.com", ""),
    ("harpers-bazaar-korea", "Harper's Bazaar Korea", "한국", "한국판 패션", "https://www.harpersbazaar.co.kr", ""),
    ("elle-korea", "Elle Korea", "한국", "한국판 패션", "https://www.elle.co.kr", "주소는 제3자 목록으로만 확인"),
    ("marie-claire-korea", "Marie Claire Korea", "한국", "한국판 패션", "https://www.marieclairekorea.com", ""),
    ("dazed-korea", "Dazed Korea", "한국", "한국판 패션·컬처", None, "현재 공식 주소를 확인하지 못함"),
]

# 잡지 키워드: 레이아웃 / 타이포그래피 / 이미지 / 색상. 용어는 catalog_vocab.py 에 있는 것만 쓴다.
# Claude 가 각 잡지의 잘 알려진 편집 특징(주로 표지·마스트헤드)을 정리한 것이다. 확신이 없는 칸은 비워 둔다.
# 한국판은 본판과 같은 마스트헤드를 쓰므로 타이포그래피를 본판에서 따랐다.
VOGUE_T = ["디돈 세리프", "고대비 획", "올캡스"]
KEYWORDS = {
    "vogue": (["풀블리드", "마스트헤드 상단 배치", "마스트헤드 오버랩", "커버라인"], VOGUE_T, ["셀러브리티 커버", "스튜디오", "미디엄 숏"], []),
    "harpers-bazaar": (["화이트 스페이스", "마스트헤드 상단 배치", "커버라인"], ["디돈 세리프", "고대비 획", "넓은 트래킹"],
                       ["셀러브리티 커버", "스튜디오", "전신 숏"], []),
    "elle": (["풀블리드", "마스트헤드 상단 배치", "커버라인"], ["디돈 세리프", "고대비 획", "올캡스"], ["셀러브리티 커버", "스튜디오", "클로즈업"], []),
    "w-magazine": (["풀블리드", "마스트헤드 상단 배치"], ["모노그램 마스트헤드"], ["셀러브리티 커버", "스튜디오"], []),
    "interview": (["풀블리드", "마스트헤드 상단 배치"], ["핸드레터링"], ["셀러브리티 커버", "클로즈업"], []),
    "numero": (["풀블리드", "마스트헤드 상단 배치"], [], ["스튜디오"], []),
    "cr-fashion-book": (["풀블리드"], [], ["셀러브리티 커버", "스튜디오"], []),
    "i-d": (["풀블리드", "마스트헤드 상단 배치"], ["그로테스크 산세리프"], ["윙크 커버", "클로즈업"], []),
    "dazed": (["풀블리드"], ["그로테스크 산세리프", "볼드 웨이트"], ["콘셉추얼 화보"], []),
    "another": (["화이트 스페이스", "풀블리드"], [], ["콘셉추얼 화보"], []),
    "the-face": (["비대칭 레이아웃"], ["실험적 타이포그래피", "그로테스크 산세리프"], ["스트리트 스타일"], []),
    "love": (["풀블리드"], ["올캡스"], ["셀러브리티 커버", "스튜디오"], []),
    "pop": ([], [], ["셀러브리티 커버"], []),
    "purple": (["화이트 스페이스", "미니멀 레이아웃"], [], ["플래시", "스냅숏 미학"], []),
    "system": (["텍스트 중심 지면", "미니멀 레이아웃"], [], [], []),
    "032c": ([], ["그로테스크 산세리프", "볼드 웨이트"], [], ["시그니처 레드"]),
    "re-edition": ([], [], [], []),
    "fantastic-man": (["텍스트 중심 지면", "화이트 스페이스"], [], ["포트레이트"], []),
    "the-gentlewoman": (["화이트 스페이스"], [], ["포트레이트", "자연광"], []),
    "document-journal": (["풀블리드"], [], ["콘셉추얼 화보"], []),
    "self-service": (["미니멀 레이아웃"], [], [], []),
    "kinfolk": (["화이트 스페이스", "넓은 마진", "미니멀 레이아웃"], [], ["자연광", "정물", "실내 장면"], []),
    "apartamento": ([], [], ["실내 장면", "자연광", "스냅숏 미학"], []),
    "vogue-korea": (["풀블리드", "마스트헤드 상단 배치", "커버라인"], VOGUE_T, ["셀러브리티 커버", "스튜디오"], []),
    "w-korea": (["풀블리드", "마스트헤드 상단 배치"], ["모노그램 마스트헤드"], ["셀러브리티 커버", "스튜디오"], []),
    "harpers-bazaar-korea": (["마스트헤드 상단 배치", "커버라인"], ["디돈 세리프", "고대비 획"], ["셀러브리티 커버", "스튜디오"], []),
    "elle-korea": (["마스트헤드 상단 배치", "커버라인"], ["디돈 세리프", "고대비 획"], ["셀러브리티 커버", "스튜디오"], []),
    "marie-claire-korea": (["마스트헤드 상단 배치", "커버라인"], [], ["셀러브리티 커버"], []),
    "dazed-korea": (["풀블리드"], ["그로테스크 산세리프", "볼드 웨이트"], ["콘셉추얼 화보"], []),
}
COMP_KEYS = ("layout", "typography", "image", "colour_tags")


def check_keywords() -> None:
    import catalog_vocab as V
    slugs = {m[0] for m in MAGAZINES}
    errors = [f"{slug}: unknown magazine" for slug in KEYWORDS if slug not in slugs]
    errors += [f"{slug}: no keywords entry" for slug in slugs if slug not in KEYWORDS]
    for slug, comps in KEYWORDS.items():
        for comp, tags in zip(COMP_KEYS, comps):
            bad = V.unknown_tags(comp, tags)
            if bad:
                errors.append(f"{slug}: {comp} terms not in catalog_vocab.py: {bad}")
    if errors:
        raise SystemExit("keyword errors:\n  " + "\n  ".join(errors))


COMPONENTS = [  # (이름, 검색어 꼬리) -- 잡지명 뒤에 붙인다
    ("레이아웃", "magazine layout spread"),
    ("타이포그래피", "magazine typography masthead"),
    ("이미지", "magazine editorial photography"),
    ("색상", "magazine cover"),
]
SEARCH = [("핀터레스트", "https://www.pinterest.com/search/pins/?q={q}"),
          ("구글 이미지", "https://www.google.com/search?tbm=isch&q={q}")]


# --------------------------------------------------------------------------- fetch (runs on the Mac)

class _Meta(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = {}

    def handle_starttag(self, tag, attrs):
        if tag != "meta":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        key = (a.get("property") or a.get("name") or "").lower()
        if key in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src") and a.get("content"):
            self.found.setdefault(key, a["content"].strip())


def find_preview_image(page_html: str, base_url: str) -> "str | None":
    p = _Meta()
    p.feed(page_html)
    for key in ("og:image:secure_url", "og:image", "twitter:image", "twitter:image:src"):
        if key in p.found:
            url = urllib.parse.urljoin(base_url, p.found[key])
            if urllib.parse.urlparse(url).scheme in ("http", "https"):
                return url
    return None


def _get(opener, url: str, limit: int, accept: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with opener(req, timeout=20) as r:
        body = r.read(limit + 1)
        if len(body) > limit:
            raise ValueError(f"response larger than {limit} bytes")
        return r.headers.get("Content-Type", ""), body, r.geturl()


def robots_allows(opener, url: str) -> bool:
    parts = urllib.parse.urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        _, body, _ = _get(opener, f"{parts.scheme}://{parts.netloc}/robots.txt", 512 * 1024, "text/plain")
        rp.parse(body.decode("utf-8", "replace").splitlines())
    except Exception:
        return True  # no readable robots.txt: allowed by convention
    return rp.can_fetch(UA, url)


def fetch(cache: Path = CACHE, opener=urllib.request.urlopen, sleep=time.sleep, only=None) -> dict:
    from PIL import Image  # needed only here
    (cache / "images").mkdir(parents=True, exist_ok=True)
    meta_path = cache / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    for slug, name, _, _, url, _ in MAGAZINES:
        if only and slug not in only:
            continue
        rec = {"site": url, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if not url:
            meta[slug] = {**rec, "status": "no_official_url"}
            continue
        try:
            if not robots_allows(opener, url):
                meta[slug] = {**rec, "status": "robots_disallow"}
                continue
            sleep(INTERVAL)
            ctype, body, final = _get(opener, url, MAX_HTML, "text/html")
            img_url = find_preview_image(body.decode("utf-8", "replace"), final)
            if not img_url:
                meta[slug] = {**rec, "status": "no_preview_image"}
                continue
            sleep(INTERVAL)
            ctype, data, _ = _get(opener, img_url, MAX_IMAGE, "image/*")
            if not ctype.lower().startswith("image/"):
                raise ValueError(f"preview is not an image ({ctype})")
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                im = im.convert("RGB")
                im.thumbnail((1200, 1200))
                im.save(cache / "images" / f"{slug}.jpg", "JPEG", quality=84)
            meta[slug] = {**rec, "status": "ok", "preview_image_url": img_url}
        except (urllib.error.URLError, OSError, ValueError) as e:
            meta[slug] = {**rec, "status": "error", "error": f"{type(e).__name__}: {e}"[:300]}
        print(f"{slug:24} {meta[slug]['status']}", flush=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


# --------------------------------------------------------------------------- build

def build(cache: Path = CACHE, out: Path = PROJECT / "magazine_urls.html", embed: bool = True,
          fragment: bool = False) -> dict:
    """fragment=True drops the <html>/<head>/<body> wrapper (for hosts that add their own)."""
    import catalog_vocab as V
    check_keywords()
    meta_path = cache / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    e = html.escape
    groups, with_image = {}, 0
    for slug, name, country, kind, url, note in MAGAZINES:
        img_path = cache / "images" / f"{slug}.jpg"
        palette_html = '<p class="muted">대표 이미지를 받으면 색을 측정합니다</p>'
        measured = []
        if img_path.exists():
            with_image += 1
            src = ("data:image/jpeg;base64," + base64.b64encode(img_path.read_bytes()).decode("ascii")) if embed \
                else f"{cache.name}/images/{slug}.jpg"
            visual = f'<img src="{e(src)}" alt="{e(name)} 대표 이미지" loading="lazy">'
            try:
                import catalog_measure
                m = catalog_measure.measure(img_path)
                sw = "".join(f'<span class="sw" style="background:{c["hex"]}" title="{c["hex"]}"></span>' for c in m["palette"])
                palette_html = (f'<div class="sws">{sw}</div><p class="hex">{" ".join(c["hex"] for c in m["palette"])}</p>'
                                f'<p class="measured">대표 이미지에서 측정</p>')
                measured = [m["scheme"], m["key"], m["contrast"], m["chroma"]]
            except Exception:
                pass
        else:
            status = (meta.get(slug) or {}).get("status")
            why = {"robots_disallow": "사이트가 수집을 허용하지 않음", "no_preview_image": "사이트에 대표 이미지가 없음",
                   "no_official_url": "공식 사이트 없음", "error": "받기 실패"}.get(status, "아직 받지 않음")
            visual = f'<div class="ph"><span>{e(name)}</span><small>{e(why)}</small></div>'
        rows, all_tags = [], []
        kw = KEYWORDS.get(slug, ([], [], [], []))
        for (label, tail), comp, tags in zip(COMPONENTS, COMP_KEYS, kw):
            q = f"{name} {tail}"
            links = "".join(f'<a href="{e(t.format(q=quote_plus(q)))}" target="_blank" rel="noopener">{e(n)} ↗</a>'
                            for n, t in SEARCH)
            if comp == "colour_tags":
                tags = measured + list(tags)
            all_tags += [f"{label}:{t}" for t in tags]
            chips = "".join(f'<button type="button" class="tag" data-tag="{e(label)}:{e(t)}" title="{e(V.ENGLISH.get(t, ""))}">'
                            f'{e(t)}</button>' for t in tags) or '<span class="muted">미정</span>'
            extra = palette_html if comp == "colour_tags" else ""
            rows.append(f'<div class="row"><dt>{e(label)}</dt><dd><div class="tags">{chips}</div>{extra}'
                        f'<div class="links">{links}</div></dd></div>')
        site = (f'<a class="url" href="{e(url)}" target="_blank" rel="noopener">{e(url.split("//", 1)[1])}</a>'
                if url else '<span class="muted">공식 URL 확인 안 됨</span>')
        empty = "" if img_path.exists() else " empty"
        card = (f'<article class="mag" data-text="{e((name + " " + country + " " + kind).lower())}" '
                f'data-tags="{e("|".join(all_tags))}">'
                f'<a class="visual{empty}" href="{e(url or "#")}" target="_blank" rel="noopener">{visual}</a>'
                f'<h3>{e(name)}</h3><p class="sub">{e(country)} · {e(kind)}</p>{site}'
                f'{f"<p class=note>{e(note)}</p>" if note else ""}<dl>{"".join(rows)}</dl></article>')
        groups.setdefault(kind.split("·")[0] if kind.startswith("한국판") else kind, []).append(card)
    order = ["글로벌 패션", "패션", "패션·컬처", "패션·아트", "패션 저널", "남성 패션", "여성 패션·컬처",
             "라이프스타일", "인테리어·라이프스타일", "한국판 패션", "한국판 패션·컬처"]
    sections = "".join(f'<section><h2>{e(k)} <span>{len(v)}</span></h2><div class="grid">{"".join(v)}</div></section>'
                       for k, v in sorted(groups.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99))
    page = PAGE.format(n=len(MAGAZINES), with_image=with_image, sections=sections)
    if fragment:
        page = page.split("<head>", 1)[1].replace("</head><body>", "").replace("</body></html>", "")
        page = page.replace('<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">\n', "")
    out.write_text(page, encoding="utf-8")
    return {"out": str(out), "magazines": len(MAGAZINES), "with_image": with_image, "bytes": out.stat().st_size}


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>매거진 URL 카탈로그</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: black-and-white catalogue of magazines. Card = representative image, title, official URL,
   then four component rows (layout / typography / image / colour) with reference links. */
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
.dek{{color:var(--muted);max-width:70ch;margin:0}}
input{{width:100%;box-sizing:border-box;padding:12px 14px;font:inherit;border:1.5px solid var(--ink);border-radius:0;background:var(--paper);color:var(--ink)}}
h2{{font:700 22px var(--sans);margin:0 0 14px;border-top:1px solid var(--ink);padding-top:10px}} h2 span{{font:400 12px var(--mono);color:var(--muted)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:36px 24px}}
.mag{{display:grid;gap:8px;align-content:start;min-width:0}}
.visual{{display:block;border:1px solid var(--ink);aspect-ratio:4/5;overflow:hidden;background:var(--soft);max-width:100%;
  color:var(--paper);text-decoration:none}} .visual.empty{{aspect-ratio:5/2}}
.visual img{{width:100%;height:100%;object-fit:cover;display:block}}
.ph{{height:100%;display:grid;place-content:center;text-align:center;gap:6px;padding:12px;background:var(--ink);color:var(--paper)}}
.ph span{{font:700 28px/1.05 var(--sans);letter-spacing:-.02em}} .ph small{{font:400 11px var(--mono);opacity:.7}}
h3{{font:700 20px/1.2 var(--sans);margin:4px 0 0}} .sub{{margin:0;font:400 12px var(--mono);color:var(--muted)}}
.url{{font:500 13px var(--mono);color:var(--ink);overflow-wrap:anywhere}} .note{{margin:0;font-size:12px;color:var(--muted)}}
dl{{margin:4px 0 0;border-top:1px solid var(--ink)}} .row{{display:grid;grid-template-columns:76px 1fr;gap:10px;padding:7px 0;border-bottom:1px solid var(--soft)}}
dt{{font:500 11px var(--mono);color:var(--muted);padding-top:2px}} dd{{margin:0;min-width:0}}
.tags{{display:flex;flex-wrap:wrap;gap:4px}}
.tag{{font:inherit;font-size:12px;border:1px solid var(--ink);background:var(--paper);color:var(--ink);padding:1px 6px;cursor:pointer}}
.tag[aria-pressed="true"]{{background:var(--ink);color:var(--paper)}}
.links{{display:flex;flex-wrap:wrap;gap:8px;margin-top:5px}} .links a{{font:400 11px var(--mono);color:var(--muted)}}
.bar{{position:sticky;top:env(safe-area-inset-top,0px);background:var(--paper);z-index:2;padding-block:10px;border-bottom:1px solid var(--soft);
  display:flex;flex-wrap:wrap;gap:8px;align-items:center}} .bar .now{{font:500 12px var(--mono);color:var(--muted)}}
.bar button{{font:inherit;font-size:13px;background:none;border:1.5px solid var(--ink);color:var(--ink);padding:3px 10px;cursor:pointer}}
.sws{{display:flex;height:18px;border:1px solid var(--ink);margin-top:6px}} .sw{{flex:1}}
.hex,.measured{{margin:2px 0 0;font:400 11px var(--mono);color:var(--muted);overflow-wrap:anywhere}}
.muted{{color:var(--muted);font-size:12px;margin:4px 0 0}} a:focus-visible,input:focus-visible{{outline:3px solid var(--ink);outline-offset:2px}}
</style></head><body><div class="wrap">
<header class="mast"><p class="kicker">MAGAZINE URL CATALOGUE · {n} TITLES · 대표 이미지 {with_image}</p>
<h1>매거진 URL 카탈로그</h1>
<p class="dek">잡지마다 공식 URL과 레이아웃·타이포그래피·이미지·색상 레퍼런스 링크를 함께 모았습니다. 대표 이미지는 각 잡지 공식 사이트가
링크 미리보기용으로 지정한 이미지(og:image)이고, 색상 키워드는 그 이미지에서 측정했습니다. 레이아웃·타이포그래피·이미지 키워드는
각 잡지의 잘 알려진 편집 특징(주로 표지와 마스트헤드)을 Claude가 전문용어로 정리한 것으로, 호마다 다를 수 있고 확신이 없는 칸은 "미정"으로 두었습니다.
키워드를 누르면 그 키워드를 모두 가진 잡지만 남습니다. 대표 이미지의 저작권은 각 잡지에 있으니 개인 참고용으로만 쓰세요.</p></header>
<input id="f" type="search" placeholder="잡지 거르기 (예: Vogue, 한국, 컬처)" aria-label="잡지 거르기">
<div class="bar"><span class="now" id="now">선택한 키워드 없음</span><button type="button" id="clear" hidden>선택 해제</button></div>
{sections}
</div><script>
(function(){{var active=new Set(),f=document.getElementById('f'),now=document.getElementById('now'),clear=document.getElementById('clear');
function apply(){{var q=f.value.trim().toLowerCase(),shown=0;
  document.querySelectorAll('.mag').forEach(function(m){{var tags=m.dataset.tags.split('|'),ok=m.dataset.text.indexOf(q)>-1;
    active.forEach(function(t){{if(tags.indexOf(t)<0)ok=false;}});m.hidden=!ok;if(ok)shown++;}});
  document.querySelectorAll('section').forEach(function(s){{s.hidden=!s.querySelector('.mag:not([hidden])');}});
  document.querySelectorAll('.tag').forEach(function(b){{b.setAttribute('aria-pressed',active.has(b.dataset.tag)?'true':'false');}});
  now.textContent=active.size?Array.from(active).map(function(t){{return t.split(':')[1];}}).join(' ∩ ')+' · '+shown+'곳':'선택한 키워드 없음';
  clear.hidden=!active.size;}}
document.addEventListener('click',function(ev){{var b=ev.target.closest('.tag');if(!b)return;var t=b.dataset.tag;
  if(active.has(t))active.delete(t);else active.add(t);apply();}});
clear.addEventListener('click',function(){{active.clear();apply();}});f.addEventListener('input',apply);apply();}})();
</script></body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("fetch", "build"))
    ap.add_argument("--out", type=Path, default=PROJECT / "magazine_urls.html")
    ap.add_argument("--no-embed", action="store_true", help="link images from magazine_urls/images instead of embedding")
    ap.add_argument("--fragment", action="store_true", help="omit the html/head/body wrapper")
    a = ap.parse_args(argv)
    if a.command == "fetch":
        meta = fetch()
        ok = sum(1 for v in meta.values() if v.get("status") == "ok")
        print(f"preview images: {ok}/{len(MAGAZINES)} -> {CACHE / 'images'}")
    r = build(out=a.out, embed=not a.no_embed, fragment=a.fragment)
    print(f"{r['magazines']} magazines, {r['with_image']} with image -> {r['out']} ({r['bytes'] // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
