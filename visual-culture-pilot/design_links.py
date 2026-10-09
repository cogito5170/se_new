#!/usr/bin/env python3
"""레이아웃 · 타이포그래피 · 이미지 · 색상 레퍼런스 카탈로그를 만든다 (키워드마다 표지 그림 + 검색 링크).

    python3 design_links.py          # writes design_links.html next to this file

링크만 만든다. 아무것도 받아 오지 않는다. 키워드나 사이트를 늘리려면 아래 목록을 고친다.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

from covers import COVER_FONTS, cover_svg
from moodboard_links import url_for

MOODBOARD_URL = "https://claude.ai/artifact/LX57vbjoiAiXS6W6szbsiL"

# 사이트: (이름, URL 틀, 설명, 쓰는 검색어) -- 검색어 en=영어, ko=한국어, font=구글 폰츠용 서체 이름
PINTEREST = ("핀터레스트", "https://www.pinterest.com/search/pins/?q={q}", "스크랩·무드보드", "en")
BEHANCE = ("비핸스", "https://www.behance.net/search/projects?search={q}", "디자이너 프로젝트", "en")
DRIBBBLE = ("드리블", "https://dribbble.com/search/{q}", "그래픽·UI 작업", "en")
GOOGLE = ("구글 이미지", "https://www.google.com/search?tbm=isch&q={p}", "가장 넓게 찾기", "en")
NAVER = ("네이버 이미지", "https://search.naver.com/search.naver?where=image&query={p}", "국내 결과 (한국어 검색)", "ko")
YOUTUBE = ("유튜브", "https://www.youtube.com/results?search_query={p}", "작업 과정·해설 영상", "en")
WIKI = ("위키백과", "https://en.wikipedia.org/w/index.php?search={p}", "서체·사조의 역사 (영문)", "en")
GFONTS = ("구글 폰츠", "https://fonts.google.com/?query={q}", "무료 서체 바로 보기", "font")

UNSPLASH = ("언스플래시", "https://unsplash.com/s/photos/{h}", "무료 사진", "en")
PEXELS = ("펙셀스", "https://www.pexels.com/search/{q}/", "무료 사진", "en")
FLICKR = ("플리커", "https://www.flickr.com/search/?text={p}", "사진가 원본", "en")

# 탭: id -> (탭 이름, 설명, 사이트, {분류: [(보이는 키워드, 영어 검색어, 한국어 검색어[, 구글 폰츠 검색어])]})
BOOKS = {
    "layout": ("① 레이아웃", "지면과 화면을 나누고 배치하는 법", [PINTEREST, BEHANCE, DRIBBBLE, GOOGLE, NAVER, YOUTUBE], {
        "기본 원리": [
            ("격자 나누기 (그리드)", "grid system graphic design", "그리드 시스템 디자인"),
            ("칸칸이 나눈 모듈 그리드", "modular grid layout", "모듈러 그리드"),
            ("비대칭 배치", "asymmetric layout design", "비대칭 레이아웃"),
            ("여백 살리기", "white space layout design", "여백 디자인"),
            ("중요한 것부터 크게 (위계)", "visual hierarchy layout", "시각적 위계 레이아웃"),
            ("줄 맞추기 (정렬)", "alignment layout design", "정렬 레이아웃"),
        ],
        "잡지·책": [
            ("잡지 표지", "magazine cover layout", "잡지 표지 레이아웃"),
            ("잡지 펼침면", "magazine spread layout", "잡지 펼침면"),
            ("사진으로 꽉 채운 지면", "full bleed layout", "풀블리드 레이아웃"),
            ("2단·3단 나누기", "multi column editorial layout", "다단 편집 디자인"),
            ("책 내지", "book layout design", "책 내지 디자인"),
            ("목차 디자인", "table of contents design magazine", "목차 디자인"),
        ],
        "포스터·인쇄물": [
            ("글자 중심 포스터", "typographic poster", "타이포그래피 포스터"),
            ("사진 중심 포스터", "photo poster layout", "사진 포스터 디자인"),
            ("전시 포스터", "exhibition poster design", "전시 포스터"),
            ("리플렛·브로슈어", "brochure layout design", "브로슈어 디자인"),
        ],
        "화면 (웹·앱)": [
            ("첫 화면 랜딩 페이지", "landing page layout", "랜딩페이지 디자인"),
            ("도시락처럼 나눈 벤토 그리드", "bento grid layout", "벤토 그리드"),
            ("카드 배치", "card layout ui", "카드 UI 디자인"),
            ("잡지 같은 웹사이트", "editorial website design", "에디토리얼 웹 디자인"),
            ("포트폴리오 웹사이트", "portfolio website layout", "포트폴리오 웹사이트"),
            ("모바일 앱 화면", "mobile app ui layout", "모바일 앱 UI"),
        ],
        "발표·SNS": [
            ("발표 자료", "presentation slide design", "프레젠테이션 디자인"),
            ("인스타그램 피드", "instagram feed layout", "인스타 피드 디자인"),
            ("넘겨 보는 카드뉴스", "carousel post design", "카드뉴스 디자인"),
        ],
    }),
    "type": ("② 타이포그래피", "서체 종류, 한글 서체, 글자 디자인", [GFONTS, PINTEREST, BEHANCE, GOOGLE, NAVER, WIKI, YOUTUBE], {
        "서체 종류": [
            ("삐침이 있는 세리프", "serif typeface", "세리프 서체", "Serif"),
            ("삐침이 없는 산세리프", "sans serif typeface", "산세리프 서체", "Sans"),
            ("패션 잡지 제목체 (디도·보도니)", "Didone typeface", "디도 서체", "Bodoni"),
            ("고전적인 가라몽", "Garamond typeface", "가라몽 서체", "Garamond"),
            ("단단한 그로테스크", "grotesque typeface", "그로테스크 서체", "Grotesk"),
            ("동그란 기하학 산세리프", "geometric sans serif typeface", "기하학 산세리프", "Jost"),
            ("타자기 같은 고정폭", "monospace typeface", "고정폭 서체", "Mono"),
            ("굵고 각진 슬랩 세리프", "slab serif typeface", "슬랩 세리프", "Slab"),
            ("필기체 스크립트", "script typeface", "스크립트 서체", "Script"),
            ("제목용 장식 서체", "display typeface", "디스플레이 서체"),
        ],
        "한글 서체": [
            ("명조체", "Korean serif font myeongjo", "명조체", "Myeongjo"),
            ("바탕체", "Korean batang font", "바탕체", "Batang"),
            ("고딕체", "Korean sans serif font", "고딕체", "Gothic"),
            ("둥근 돋움체", "Korean rounded font dotum", "돋움체", "Dodum"),
            ("손글씨체", "Korean handwriting font", "손글씨 폰트", "Pen"),
            ("굵은 제목용 한글", "Korean display font bold", "제목용 한글 폰트", "Black Han Sans"),
            ("레트로 한글", "retro Korean typography", "레트로 한글 폰트"),
            ("한글 레터링", "Korean lettering design", "한글 레터링"),
        ],
        "유명 서체": [
            ("헬베티카", "Helvetica typeface in use", "헬베티카"),
            ("퓨추라", "Futura typeface in use", "퓨추라 서체"),
            ("보도니", "Bodoni typeface", "보도니 서체", "Bodoni Moda"),
            ("유니버스", "Univers typeface", "유니버스 서체"),
            ("길 산스", "Gill Sans typeface", "길산스 서체"),
            ("인터", "Inter typeface", "인터 폰트", "Inter"),
        ],
        "글자 디자인": [
            ("잡지 로고 (마스트헤드)", "magazine masthead typography", "잡지 로고 타이포그래피"),
            ("아주 큰 글자", "oversized typography design", "큰 글씨 타이포그래피"),
            ("실험적인 글자 배치", "experimental typography", "실험적 타이포그래피"),
            ("서체 짝짓기", "font pairing", "폰트 조합"),
            ("두께가 변하는 가변 폰트", "variable font design", "가변 폰트"),
            ("글자 사이 간격 (자간)", "kerning typography", "자간 조절"),
            ("크기로 만드는 위계", "typographic hierarchy", "타이포그래피 위계"),
            ("로고용 레터링", "custom lettering logo", "레터링 디자인"),
        ],
    }),
    "image": ("③ 이미지", "사진, 그래픽 처리, 일러스트, 그래픽 사조",
              [PINTEREST, BEHANCE, GOOGLE, NAVER, UNSPLASH, PEXELS, FLICKR, YOUTUBE], {
        "사진": [
            ("스튜디오 화보", "studio fashion photography", "스튜디오 화보"),
            ("플래시 터뜨린 사진", "flash photography fashion", "플래시 사진"),
            ("필름 카메라 느낌", "film photography", "필름 사진"),
            ("흑백 사진", "black and white photography", "흑백 사진"),
            ("제품 정물 사진", "still life product photography", "정물 사진"),
            ("야외 로케이션", "outdoor location photography", "야외 촬영 화보"),
            ("길거리 스냅", "street photography", "스트릿 스냅"),
            ("얼굴 클로즈업", "portrait close up photography", "클로즈업 인물 사진"),
            ("전신 컷", "full body portrait photography", "전신 사진"),
            ("움직임이 번진 사진", "motion blur photography", "모션 블러 사진"),
        ],
        "그래픽 처리": [
            ("두 가지 색 (듀오톤)", "duotone photo", "듀오톤 사진"),
            ("망점 (하프톤)", "halftone graphic", "하프톤 그래픽"),
            ("거친 그레인 질감", "grain texture photo", "그레인 질감"),
            ("오려 붙인 콜라주", "collage art", "콜라주 아트"),
            ("사람만 오려 낸 컷아웃", "cutout photo graphic design", "누끼 그래픽"),
            ("크롬 금속 효과", "chrome 3d graphic", "크롬 그래픽"),
            ("3D 그래픽", "3d render graphic", "3D 그래픽"),
            ("그라디언트", "gradient graphic", "그라디언트 그래픽"),
        ],
        "일러스트": [
            ("손그림", "hand drawn illustration", "손그림 일러스트"),
            ("선으로만 그린 라인 드로잉", "line drawing illustration", "라인 드로잉"),
            ("평면 벡터 일러스트", "flat vector illustration", "플랫 일러스트"),
            ("리소 인쇄 느낌", "risograph print", "리소그래피"),
            ("픽셀 아트", "pixel art", "픽셀 아트"),
        ],
        "그래픽 사조": [
            ("스위스 스타일", "swiss style graphic design", "스위스 스타일 디자인"),
            ("바우하우스", "bauhaus graphic design", "바우하우스 디자인"),
            ("러시아 구성주의 포스터", "russian constructivism poster", "구성주의 포스터"),
            ("아르데코", "art deco graphic design", "아르데코 디자인"),
            ("60년대 사이키델릭", "psychedelic 60s poster", "사이키델릭 포스터"),
            ("80년대 멤피스", "memphis design graphic", "멤피스 디자인"),
            ("거칠고 투박한 브루탈리즘", "brutalist graphic design", "브루탈리즘 디자인"),
            ("Y2K 그래픽", "y2k graphic design", "Y2K 그래픽"),
        ],
    }),
    "color": ("④ 색상", "배색과 색 고르기", [PINTEREST, BEHANCE, DRIBBBLE, GOOGLE, NAVER, YOUTUBE], {
        "배색": [
            ("흑백", "black and white color scheme design", "흑백 배색"),
            ("한 가지 색 모노톤", "monochromatic color palette", "모노톤 배색"),
            ("같은 계열 톤온톤", "tone on tone color", "톤온톤 배색"),
            ("두 가지 색 대비", "two color palette design", "투톤 배색"),
            ("반대 색 보색 대비", "complementary colors design", "보색 대비"),
            ("강렬한 원색", "primary colors design", "원색 디자인"),
            ("파스텔", "pastel color palette", "파스텔 배색"),
            ("채도 낮은 색", "muted color palette", "저채도 배색"),
            ("형광색", "neon color palette", "형광색 배색"),
            ("차분한 흙빛 어스톤", "earth tone color palette", "어스톤 배색"),
            ("금속 느낌 금·은", "metallic gold silver design", "메탈릭 컬러"),
        ],
        "색 고르기": [
            ("색상환", "color wheel", "색상환"),
            ("컬러 팔레트 모음", "color palette inspiration", "컬러 팔레트"),
            ("그라디언트 배색", "gradient color palette", "그라디언트 배색"),
            ("브랜드 컬러", "brand color palette", "브랜드 컬러"),
            ("패션 컬러 트렌드", "fashion color trends", "패션 컬러 트렌드"),
            ("팬톤 같은 컬러 칩", "pantone color chips", "팬톤 컬러칩"),
        ],
    }),
}

HUBS = [
    ("디자인 작업 모음", [
        ("비핸스", "https://www.behance.net"), ("드리블", "https://dribbble.com"),
        ("노트폴리오 (국내)", "https://notefolio.net"), ("잇츠 나이스 댓", "https://www.itsnicethat.com"),
        ("브랜드 뉴 (로고·리브랜딩 리뷰)", "https://www.underconsideration.com/brandnew/"),
    ]),
    ("무드보드 모으는 곳", [
        ("아레나 (Are.na)", "https://www.are.na"), ("사비 (Savee)", "https://savee.it"),
        ("코스모스 (Cosmos)", "https://www.cosmos.so"), ("디자인스퍼레이션", "https://www.designspiration.com"),
    ]),
    ("폰트", [
        ("구글 폰츠 (무료)", "https://fonts.google.com"), ("눈누 (무료 한글 폰트)", "https://noonnu.cc"),
        ("어도비 폰트", "https://fonts.adobe.com"), ("폰츠 인 유즈 (쓰인 사례)", "https://fontsinuse.com"),
        ("타입울프 (서체 추천)", "https://www.typewolf.com"), ("마이폰츠", "https://www.myfonts.com"),
    ]),
    ("색", [
        ("쿨러스 (팔레트 만들기)", "https://coolors.co"), ("어도비 컬러", "https://color.adobe.com"),
        ("컬러 헌트 (팔레트 모음)", "https://colorhunt.co"),
    ]),
    ("무료 사진", [
        ("언스플래시", "https://unsplash.com"), ("펙셀스", "https://www.pexels.com"),
    ]),
    ("웹·앱 화면", [
        ("어워드 (Awwwards)", "https://www.awwwards.com"), ("랜드북 (랜딩 페이지)", "https://land-book.com"),
        ("원 페이지 러브", "https://onepagelove.com"), ("모빈 (앱 화면)", "https://mobbin.com"),
    ]),
    ("같이 보기", [("패션 무드보드 색인", MOODBOARD_URL)]),
]


def query_for(kw: tuple, lang: str) -> "str | None":
    ko, en, ko_q = kw[:3]
    if lang == "font":
        return kw[3] if len(kw) > 3 else None
    return ko_q if lang == "ko" else en


def build() -> str:
    e = html.escape
    tabs, panels, total_kw, total_links, uid = [], [], 0, 0, 0
    for i, (bid, (label, dek, sites, cats)) in enumerate(BOOKS.items()):
        n_kw = sum(len(v) for v in cats.values())
        total_kw += n_kw
        tabs.append(f'<a class="tab" href="#{bid}" data-tab="{bid}">{e(label)} <span>{n_kw}</span></a>')
        groups = []
        for cat, kws in cats.items():
            cards = []
            for kw in kws:
                uid += 1
                links = []
                for name, tpl, _, lang in sites:
                    q = query_for(kw, lang)
                    if q:
                        links.append((name, url_for(tpl, q)))
                total_links += len(links)
                first = next(u for n, u in links if n == PINTEREST[0])
                chips = "".join(f'<a href="{e(u)}" target="_blank" rel="noopener">{e(n)}</a>' for n, u in links)
                terms = " · ".join(x for x in kw[1:] if x)
                cards.append(
                    f'<li class="card" data-text="{e(" ".join([cat] + [x for x in kw if x]).lower())}">'
                    f'<a class="cover{" colour" if bid == "color" else ""}" href="{e(first)}" target="_blank" rel="noopener" '
                    f'aria-label="{e(kw[0])} 핀터레스트 검색">{cover_svg(kw[0], str(uid))}</a>'
                    f'<div class="meta"><p class="label"><span class="cat">{e(cat)} /</span> {e(kw[0])}</p>'
                    f'<p class="q">{e(terms)}</p><div class="chips">{chips}</div></div></li>')
            groups.append(f'<section class="group"><h2>{e(cat)} <span class="n">{len(kws)}</span></h2>'
                          f'<ul class="grid">{"".join(cards)}</ul></section>')
        site_list = "".join(f"<li><b>{e(n)}</b><span>{e(note)}</span></li>" for n, _, note, _ in sites)
        panels.append(f'<div class="panel" id="p-{bid}"{"" if i == 0 else " hidden"}>'
                      f'<p class="dek">{e(dek)}</p>{"".join(groups)}'
                      f'<section class="group"><h2>이 탭의 사이트</h2><ul class="sites">{site_list}</ul></section></div>')
    hubs = "".join(f'<div class="hub"><h3>{e(t)}</h3><ul>' + "".join(
        f'<li><a href="{e(u)}" target="_blank" rel="noopener">{e(n)}</a></li>' for n, u in items) + "</ul></div>"
        for t, items in HUBS)
    families = "&".join("family=" + f.replace(" ", "+") for f in sorted(set(COVER_FONTS) | {"IBM Plex Sans KR", "IBM Plex Mono"}))
    return f"""<title>레퍼런스 카탈로그</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{families}&display=swap">
<style>
/* Layout: black-and-white catalogue. Four numbered tabs; each category is a grid of cards, cover drawing first,
   then "분류 / 키워드", search terms and site links. Only the colour tab keeps colour in its covers. */
:root{{
  --paper:#ffffff; --ink:#000000; --muted:#5c5c5c; --rule:#000000; --soft:#e6e6e6;
  --sans:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--paper:#000000; --ink:#ffffff; --muted:#a3a3a3; --rule:#ffffff; --soft:#262626; color-scheme:dark}}}}
:root[data-theme="dark"]{{--paper:#000000; --ink:#ffffff; --muted:#a3a3a3; --rule:#ffffff; --soft:#262626; color-scheme:dark}}
[hidden]{{display:none!important}}
body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 var(--sans);padding:0 16px;padding-block:24px 56px}}
.wrap{{max-width:1180px;margin:0 auto;display:grid;gap:24px}}
header{{display:grid;gap:10px;border-bottom:3px solid var(--rule);padding-bottom:18px}}
h1{{font:700 clamp(34px,7vw,72px)/1 var(--sans);letter-spacing:-0.03em;margin:0;text-wrap:balance}}
.dek{{color:var(--muted);max-width:64ch;margin:0}}
.stats{{font:500 12px var(--mono);letter-spacing:.04em;color:var(--muted);margin:0}}
nav{{display:flex;flex-wrap:wrap;gap:8px;position:sticky;top:env(safe-area-inset-top,0px);background:var(--paper);
  padding-block:10px;z-index:2;border-bottom:1px solid var(--soft)}}
.tab{{text-decoration:none;color:var(--ink);border:1.5px solid var(--ink);padding:7px 14px;font-weight:600}}
.tab span{{font:400 12px var(--mono);color:var(--muted)}}
.tab[aria-current="true"]{{background:var(--ink);color:var(--paper)}} .tab[aria-current="true"] span{{color:var(--paper)}}
input{{width:100%;box-sizing:border-box;padding:12px 14px;font:inherit;border:1.5px solid var(--ink);border-radius:0;
  background:var(--paper);color:var(--ink)}}
input:focus-visible,a:focus-visible{{outline:3px solid var(--ink);outline-offset:2px}}
.panel{{display:grid;gap:32px}}
h2{{font:700 22px/1.2 var(--sans);margin:0 0 14px;display:flex;align-items:baseline;gap:10px;border-top:1px solid var(--rule);padding-top:10px}}
h2 .n{{font:400 12px var(--mono);color:var(--muted)}}
.grid{{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:28px 16px}}
.card{{display:grid;gap:10px;align-content:start;min-width:0}}
.cover{{display:block;border:1px solid var(--rule);line-height:0;background:#fff}}
.cover svg{{width:100%;height:auto;display:block;filter:grayscale(1)}}
.cover.colour svg{{filter:none}}
.cover:hover svg{{opacity:.85}}
.meta{{display:grid;gap:4px;min-width:0}}
.label{{margin:0;font-weight:600;line-height:1.35}} .cat{{color:var(--muted);font-weight:400}}
.q{{margin:0;font:400 11px/1.4 var(--mono);color:var(--muted);overflow-wrap:anywhere}}
.chips{{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}}
.chips a{{color:var(--ink);text-decoration:none;border:1px solid var(--ink);padding:1px 6px;font-size:12px}}
.chips a:hover{{background:var(--ink);color:var(--paper)}}
.hubs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:22px}}
.hub h3{{font:600 12px var(--mono);letter-spacing:.04em;margin:0 0 6px}}
.hub ul,.sites{{list-style:none;margin:0;padding:0;display:grid;gap:4px}}
.sites li{{display:flex;flex-wrap:wrap;gap:4px 10px}} .sites span{{color:var(--muted)}}
a{{color:var(--ink)}} .note{{font-size:13px;color:var(--muted);max-width:72ch}} .empty{{color:var(--muted)}}
@media (prefers-reduced-motion:no-preference){{.cover svg{{transition:opacity .15s}}}}
</style>
<div class="wrap">
<header>
  <p class="stats">REFERENCE CATALOGUE · 키워드 {total_kw} · 검색 링크 {total_links}</p>
  <h1>레퍼런스 카탈로그</h1>
  <p class="dek">레이아웃, 타이포그래피, 이미지, 색상 레퍼런스를 <b>분류 / 키워드</b>로 모았습니다. 그림을 누르면 핀터레스트 검색이,
  아래 사이트 이름을 누르면 그 사이트의 검색 결과가 새 탭에서 열립니다.</p>
</header>
<nav aria-label="주제">{''.join(tabs)}</nav>
<label for="f" class="stats">이 탭에서 거르기</label>
<input id="f" type="search" placeholder="예: 그리드, 명조, 필름, 파스텔">
<p class="empty" id="none" hidden>맞는 키워드가 없습니다.</p>
{''.join(panels)}
<section class="group"><h2>키워드 없이 둘러볼 곳</h2><div class="hubs">{hubs}</div></section>
<p class="note">표지 그림은 키워드의 뜻을 보여 주려고 직접 그린 것이며 실제 작업물이 아닙니다. 링크는 키워드로 만든 검색 주소이고,
만들 때 결과를 미리 확인하지 않았습니다. 찾은 작업물 대부분은 저작권이 있으니 참고용으로만 쓰세요.</p>
</div>
<script>
(function(){{
var tabs=document.querySelectorAll('.tab'),f=document.getElementById('f'),none=document.getElementById('none');
function current(){{var id=(location.hash||'').slice(1);return document.getElementById('p-'+id)?id:'layout';}}
function filter(){{var q=f.value.trim().toLowerCase(),panel=document.getElementById('p-'+current()),shown=0;
  panel.querySelectorAll('.card').forEach(function(li){{var ok=li.dataset.text.indexOf(q)>-1;li.hidden=!ok;if(ok)shown++;}});
  panel.querySelectorAll('.grid').forEach(function(ul){{ul.closest('.group').hidden=
    !Array.prototype.some.call(ul.children,function(li){{return !li.hidden;}});}});
  none.hidden=shown>0;}}
function show(){{var id=current();
  document.querySelectorAll('.panel').forEach(function(p){{p.hidden=p.id!=='p-'+id;}});
  tabs.forEach(function(t){{t.setAttribute('aria-current',t.dataset.tab===id?'true':'false');}});
  filter();}}
tabs.forEach(function(t){{t.addEventListener('click',function(ev){{ev.preventDefault();
  try{{history.replaceState(null,'','#'+t.dataset.tab);}}catch(e){{location.hash=t.dataset.tab;}} show();}});}});
window.addEventListener('hashchange',show);f.addEventListener('input',filter);show();
}})();
</script>"""


def main() -> int:
    out = Path(__file__).resolve().parent / "design_links.html"
    text = build()
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}: tabs {len(BOOKS)}, keywords {sum(sum(len(v) for v in b[3].values()) for b in BOOKS.values())}, "
          f"{len(text.encode()) // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
