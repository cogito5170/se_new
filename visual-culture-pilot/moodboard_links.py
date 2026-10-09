#!/usr/bin/env python3
"""Build a page of search links for fashion-magazine moodboard keywords across many sites.

    python3 moodboard_links.py          # writes moodboard_links.html next to this file

Only links are generated; nothing is fetched or downloaded. Edit KEYWORDS / SITES to extend.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path
from urllib.parse import quote, quote_plus

KEYWORDS = {
    "무드": ["minimal editorial", "quiet luxury editorial", "avant garde fashion editorial",
            "90s minimalism fashion", "Y2K fashion magazine", "dark romantic editorial",
            "dreamy soft focus editorial", "raw grunge editorial", "surreal fashion editorial"],
    "스타일": ["haute couture editorial", "streetwear editorial", "old money style editorial",
              "gorpcore editorial", "techwear editorial", "normcore fashion", "balletcore editorial",
              "workwear fashion editorial", "tailoring menswear editorial"],
    "시대": ["70s fashion editorial", "80s power dressing editorial", "90s supermodel editorial",
            "2000s fashion magazine", "1960s mod fashion editorial"],
    "레이아웃": ["magazine grid layout", "editorial spread layout", "magazine cover layout",
               "asymmetric magazine layout", "white space editorial layout", "collage magazine layout",
               "full bleed photo spread", "magazine table of contents design", "pull quote magazine layout"],
    "타이포그래피": ["serif headline magazine", "Didot fashion magazine typography", "bold sans serif editorial",
                 "experimental typography magazine", "typographic magazine cover", "masthead design magazine",
                 "oversized type editorial"],
    "사진": ["studio fashion photography editorial", "flash fashion photography", "film photography fashion editorial",
            "black and white fashion editorial", "still life fashion photography", "street style photography",
            "outdoor location fashion editorial"],
    "구도/포즈": ["fashion editorial pose", "close up beauty shot", "full body fashion shot",
                "cropped fashion photography", "motion blur fashion photography"],
    "컬러": ["monochrome fashion editorial", "pastel fashion editorial", "earth tone fashion moodboard",
            "high contrast color editorial", "neon fashion editorial", "red color story fashion",
            "muted color palette editorial"],
    "소재/텍스처": ["fabric texture close up", "sheer fabric editorial", "leather texture fashion",
                "knitwear editorial", "denim editorial"],
    "뷰티": ["beauty editorial makeup", "glossy skin editorial", "graphic eyeliner editorial", "hair editorial"],
    "잡지": ["Vogue editorial spread", "i-D magazine layout", "Dazed magazine layout", "The Face magazine layout",
            "Purple magazine editorial", "Self Service magazine", "Brodovitch Harper's Bazaar layout",
            "W magazine editorial", "System magazine", "Another magazine editorial", "Vogue Korea editorial"],
    "무드보드 형식": ["fashion moodboard", "moodboard layout", "collage moodboard fashion",
                  "color palette moodboard fashion", "brand moodboard fashion"],
}

# (name, URL template with {q} = %20-encoded, {p} = +-encoded, {h} = hyphenated, note)
SITES = [
    ("Pinterest", "https://www.pinterest.com/search/pins/?q={q}", "무드보드·지면 스크랩"),
    ("Behance", "https://www.behance.net/search/projects?search={q}", "디자이너 프로젝트·에디토리얼 디자인"),
    ("Google 이미지", "https://www.google.com/search?tbm=isch&q={p}", "가장 넓게"),
    ("Bing 이미지", "https://www.bing.com/images/search?q={p}", "구글과 결과가 다름"),
    ("네이버 이미지", "https://search.naver.com/search.naver?where=image&query={p}", "국내 잡지·화보"),
    ("다음 이미지", "https://search.daum.net/search?w=img&q={p}", "국내 결과"),
    ("Tumblr", "https://www.tumblr.com/search/{q}", "스캔본·아카이브 블로그"),
    ("Flickr", "https://www.flickr.com/search/?text={p}", "사진가 원본, 라이선스 필터 있음"),
    ("Unsplash", "https://unsplash.com/s/photos/{h}", "무료 사진 (Unsplash 라이선스)"),
    ("Pexels", "https://www.pexels.com/search/{q}/", "무료 사진 (Pexels 라이선스)"),
    ("Vogue.com", "https://www.vogue.com/search?q={p}", "기사·화보"),
    ("Wikimedia Commons", "https://commons.wikimedia.org/w/index.php?search={p}&title=Special:MediaSearch&type=image",
     "자유 라이선스 이미지"),
    ("Google Arts & Culture", "https://artsandculture.google.com/search?q={p}", "박물관·패션 아카이브"),
    ("Europeana", "https://www.europeana.eu/en/search?query={p}", "유럽 기관 소장품"),
    ("Internet Archive", "https://archive.org/search?query={p}", "잡지 스캔 많음, 권리 불분명한 것 다수"),
]

HUBS = [
    ("잡지 원본", [
        ("Vogue Archive (Condé Nast, 유료)", "https://archive.vogue.com"),
        ("ProQuest Vogue Archive (도서관)", "https://about.proquest.com/en/products-services/vogue_archive/"),
        ("ProQuest Women's Wear Daily Archive (도서관)", "https://about.proquest.com/en/products-services/www/"),
    ]),
    ("표지·지면 큐레이션", [
        ("Coverjunkie", "https://coverjunkie.com"),
        ("Stack Magazines", "https://stackmagazines.com"),
        ("magCulture", "https://magculture.com"),
        ("Fonts In Use", "https://fontsinuse.com"),
        ("It's Nice That", "https://www.itsnicethat.com"),
    ]),
    ("화보 크레딧·런웨이", [
        ("Vogue Runway", "https://www.vogue.com/fashion-shows"),
        ("models.com (화보·크레딧)", "https://models.com"),
        ("SHOWstudio", "https://www.showstudio.com"),
    ]),
    ("무드보드 커뮤니티", [
        ("Are.na", "https://www.are.na"),
        ("Cosmos", "https://www.cosmos.so"),
        ("Savee", "https://savee.it"),
        ("Designspiration", "https://www.designspiration.com"),
    ]),
]

HASHTAGS = ["editorialdesign", "magazinedesign", "fashioneditorial", "editoriallayout", "moodboard",
            "typography", "magazinecover", "printdesign", "fashionphotography", "artdirection"]


def url_for(template: str, keyword: str) -> str:
    return template.format(q=quote(keyword), p=quote_plus(keyword), h=quote(keyword.lower().replace(" ", "-")))


def build() -> str:
    e = html.escape
    sections = []
    for cat, kws in KEYWORDS.items():
        items = []
        for kw in kws:
            chips = "".join(f'<a href="{e(url_for(t, kw))}" target="_blank" rel="noopener">{e(name)}</a>'
                            for name, t, _ in SITES)
            items.append(f'<li class="kw" data-text="{e((cat + " " + kw).lower())}">'
                         f'<p class="label"><span class="cat">{e(cat)} /</span> {e(kw)}</p>'
                         f'<div class="chips">{chips}</div></li>')
        sections.append(f'<section class="group"><h2>{e(cat)} <span class="n">{len(kws)}</span></h2>'
                        f'<ul class="kws">{"".join(items)}</ul></section>')
    hubs = "".join(f'<div class="hub"><h3>{e(t)}</h3><ul>' + "".join(
        f'<li><a href="{e(u)}" target="_blank" rel="noopener">{e(n)}</a></li>' for n, u in items) + "</ul></div>"
        for t, items in HUBS)
    tags = "".join(f'<a href="https://www.instagram.com/explore/tags/{e(h)}/" target="_blank" rel="noopener">#{e(h)}</a>'
                   for h in HASHTAGS)
    sites = "".join(f"<li><b>{e(n)}</b><span>{e(note)}</span></li>" for n, _, note in SITES)
    n_kw = sum(len(v) for v in KEYWORDS.values())
    return f"""<title>Moodboard Index</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:opsz,wght@6..96,500;6..96,700&family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap">
<style>
/* Layout: a magazine index. Didone masthead, one column of keyword entries, site links as wrapping chips. */
:root{{
  --paper:#fbfbfd; --ink:#16171c; --muted:#62646f; --rule:#dfe0e7; --chip:#eef0f7; --accent:#2340b8;
  --display:"Bodoni Moda","Didot","Bodoni 72",Georgia,serif;
  --body:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{
  --paper:#101116; --ink:#e9eaf0; --muted:#9a9cab; --rule:#2a2c36; --chip:#1c1e27; --accent:#9db0ff; color-scheme:dark}}}}
:root[data-theme="dark"]{{--paper:#101116; --ink:#e9eaf0; --muted:#9a9cab; --rule:#2a2c36; --chip:#1c1e27; --accent:#9db0ff; color-scheme:dark}}
body{{background:var(--paper);color:var(--ink);font:15px/1.55 var(--body);padding:0 16px;padding-block:24px 48px}}
.wrap{{max-width:980px;margin:0 auto;display:grid;gap:28px}}
header{{display:grid;gap:10px;border-bottom:2px solid var(--ink);padding-bottom:16px}}
h1{{font:700 clamp(40px,9vw,84px)/0.95 var(--display);letter-spacing:-0.02em;margin:0;text-wrap:balance}}
.dek{{color:var(--muted);max-width:62ch;margin:0}}
.stats{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
input{{width:100%;box-sizing:border-box;padding:12px 14px;font:inherit;border:1px solid var(--rule);border-radius:6px;
  background:var(--paper);color:var(--ink)}}
input:focus-visible,a:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
h2{{font:500 30px/1.1 var(--display);margin:0 0 8px;display:flex;align-items:baseline;gap:10px;
  border-bottom:1px solid var(--rule);padding-bottom:6px}}
h2 .n{{font:500 12px var(--body);color:var(--muted);letter-spacing:.06em}}
.kws{{list-style:none;margin:0;padding:0;display:grid;gap:0}}
.kw{{display:grid;gap:6px;padding:12px 0;border-bottom:1px solid var(--rule);min-width:0}}
.label{{margin:0;font-weight:600}} .cat{{color:var(--muted);font-weight:400}}
.chips{{display:flex;flex-wrap:wrap;gap:6px}}
.chips a{{background:var(--chip);color:var(--accent);text-decoration:none;padding:3px 9px;border-radius:999px;font-size:13px}}
.chips a:hover{{text-decoration:underline}}
.hubs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px}}
.hub h3{{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 6px}}
.hub ul,.sites{{list-style:none;margin:0;padding:0;display:grid;gap:4px}}
.sites li{{display:flex;flex-wrap:wrap;gap:4px 10px}} .sites span{{color:var(--muted)}}
a{{color:var(--accent)}} .tags{{display:flex;flex-wrap:wrap;gap:8px 14px}}
.note{{font-size:13px;color:var(--muted);max-width:70ch}}
.empty{{color:var(--muted)}}
</style>
<div class="wrap">
<header>
  <p class="stats">Fashion magazine reference &middot; {n_kw} keywords &middot; {len(SITES)} sites</p>
  <h1>Moodboard Index</h1>
  <p class="dek">무드보드용 키워드를 <b>분류 / 키워드</b>로 정리했습니다. 사이트 이름을 누르면 그 사이트의 검색 결과가 새 탭에서 열립니다.</p>
  <label for="f" class="stats">키워드 거르기</label>
  <input id="f" type="search" placeholder="예: layout, 컬러, 90s, Vogue">
  <p class="empty" id="none" hidden>맞는 키워드가 없습니다.</p>
</header>
{''.join(sections)}
<section class="group"><h2>키워드 없이 둘러볼 곳</h2><div class="hubs">{hubs}</div></section>
<section class="group"><h2>Instagram 해시태그</h2><div class="tags">{tags}</div></section>
<section class="group"><h2>사이트 안내</h2><ul class="sites">{sites}</ul></section>
<p class="note">링크는 키워드로 만든 검색 주소이며, 만들 때 결과를 미리 확인하지 않았습니다. 사이트가 주소 형식을 바꾸면 일부가 안 맞을 수 있습니다.
여기서 찾는 이미지 대부분은 저작권이 있습니다. 개인 레퍼런스로만 쓰세요.</p>
</div>
<script>
(function(){{var f=document.getElementById('f'),none=document.getElementById('none');
f.addEventListener('input',function(){{var q=f.value.trim().toLowerCase(),shown=0;
document.querySelectorAll('.kw').forEach(function(li){{var ok=li.dataset.text.indexOf(q)>-1;li.hidden=!ok;if(ok)shown++;}});
document.querySelectorAll('.kws').forEach(function(ul){{var g=ul.closest('.group');
g.hidden=!Array.prototype.some.call(ul.children,function(li){{return !li.hidden;}});}});
none.hidden=shown>0;}});}})();
</script>"""


def main() -> int:
    out = Path(__file__).resolve().parent / "moodboard_links.html"
    out.write_text(build(), encoding="utf-8")
    n_kw = sum(len(v) for v in KEYWORDS.values())
    print(f"wrote {out}: {n_kw} keywords x {len(SITES)} sites = {n_kw * len(SITES)} search links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
