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

# 분류 -> [(화면에 보이는 한국어 키워드, 해외 사이트용 영어 검색어, 국내 사이트용 한국어 검색어)]
KEYWORDS = {
    "분위기": [
        ("미니멀한 화보", "minimal fashion editorial", "미니멀 패션 화보"),
        ("조용한 럭셔리", "quiet luxury editorial", "콰이어트 럭셔리 화보"),
        ("실험적인 아방가르드", "avant garde fashion editorial", "아방가르드 패션 화보"),
        ("몽환적이고 흐릿한", "dreamy soft focus fashion editorial", "몽환적인 패션 화보"),
        ("어둡고 로맨틱한", "dark romantic fashion editorial", "다크 로맨틱 화보"),
        ("거칠고 그런지한", "grunge fashion editorial", "그런지 패션 화보"),
        ("초현실적인", "surreal fashion editorial", "초현실 패션 화보"),
        ("따뜻한 빈티지", "vintage fashion editorial", "빈티지 패션 화보"),
    ],
    "스타일": [
        ("하이패션 오트쿠튀르", "haute couture editorial", "오트쿠튀르 화보"),
        ("스트리트 패션", "streetwear editorial", "스트릿 패션 화보"),
        ("올드머니 룩", "old money style", "올드머니 룩"),
        ("아웃도어 고프코어", "gorpcore editorial", "고프코어 룩"),
        ("테크웨어", "techwear editorial", "테크웨어 룩"),
        ("발레코어", "balletcore editorial", "발레코어 룩"),
        ("워크웨어", "workwear fashion editorial", "워크웨어 룩"),
        ("남성 수트 테일러링", "menswear tailoring editorial", "남성 수트 화보"),
        ("평범한 듯 세련된 놈코어", "normcore fashion", "놈코어 패션"),
    ],
    "시대": [
        ("60년대 모드 룩", "1960s mod fashion", "60년대 패션"),
        ("70년대 화보", "70s fashion editorial", "70년대 패션 화보"),
        ("80년대 파워 숄더", "80s power dressing", "80년대 패션"),
        ("90년대 미니멀리즘", "90s minimalism fashion", "90년대 미니멀 패션"),
        ("90년대 슈퍼모델", "90s supermodel editorial", "90년대 슈퍼모델"),
        ("Y2K 감성", "Y2K fashion magazine", "Y2K 패션 화보"),
        ("2000년대 잡지", "2000s fashion magazine", "2000년대 패션 잡지"),
    ],
    "지면 구성": [
        ("잡지 표지 디자인", "magazine cover design", "잡지 표지 디자인"),
        ("두 쪽 펼침 화보", "editorial spread layout", "잡지 펼침면 레이아웃"),
        ("격자로 짠 레이아웃", "magazine grid layout", "잡지 그리드 레이아웃"),
        ("여백을 살린 지면", "white space editorial layout", "여백 편집 디자인"),
        ("비대칭 레이아웃", "asymmetric magazine layout", "비대칭 레이아웃"),
        ("사진으로 꽉 채운 지면", "full bleed photo spread", "풀블리드 화보"),
        ("콜라주 지면", "collage magazine layout", "콜라주 편집 디자인"),
        ("목차 디자인", "magazine table of contents design", "잡지 목차 디자인"),
        ("인용문 강조", "pull quote magazine layout", "잡지 인용문 디자인"),
    ],
    "글자": [
        ("우아한 세리프 제목", "serif headline magazine", "세리프 제목 디자인"),
        ("잡지 로고(마스트헤드)", "fashion magazine masthead", "잡지 로고 디자인"),
        ("굵은 고딕 제목", "bold sans serif editorial", "굵은 고딕 편집 디자인"),
        ("아주 큰 글자", "oversized typography editorial", "큰 글씨 편집 디자인"),
        ("실험적인 글자 배치", "experimental typography magazine", "실험적 타이포그래피"),
        ("글자로만 만든 표지", "typographic magazine cover", "타이포그래피 표지"),
        ("디도 서체", "Didot fashion typography", "디도 서체"),
    ],
    "사진": [
        ("스튜디오 화보", "studio fashion photography", "스튜디오 패션 화보"),
        ("플래시 터뜨린 사진", "flash fashion photography", "플래시 패션 사진"),
        ("필름 카메라 느낌", "film photography fashion", "필름 패션 사진"),
        ("흑백 화보", "black and white fashion editorial", "흑백 패션 화보"),
        ("제품 정물 사진", "still life fashion photography", "패션 정물 사진"),
        ("야외 로케이션 화보", "outdoor fashion editorial", "야외 패션 화보"),
        ("길거리 스냅", "street style photography", "스트릿 스냅"),
    ],
    "구도와 포즈": [
        ("화보 포즈", "fashion editorial pose", "화보 포즈"),
        ("얼굴 클로즈업", "beauty close up shot", "뷰티 클로즈업"),
        ("전신 컷", "full body fashion shot", "패션 전신 사진"),
        ("과감하게 자른 구도", "cropped fashion photography", "크롭 구도 사진"),
        ("움직임이 번진 사진", "motion blur fashion photography", "모션 블러 패션 사진"),
    ],
    "색감": [
        ("한 가지 색 모노톤", "monochrome fashion editorial", "모노톤 화보"),
        ("파스텔", "pastel fashion editorial", "파스텔 화보"),
        ("차분한 흙빛", "earth tone fashion", "어스톤 패션"),
        ("강렬한 원색 대비", "high contrast color editorial", "강렬한 색감 화보"),
        ("형광색", "neon fashion editorial", "네온 패션 화보"),
        ("빨강 포인트", "red fashion editorial", "레드 화보"),
        ("채도 낮은 색감", "muted color fashion editorial", "저채도 화보"),
    ],
    "소재와 질감": [
        ("원단 클로즈업", "fabric texture close up", "원단 질감"),
        ("비치는 소재", "sheer fabric fashion", "시스루 패션"),
        ("가죽", "leather fashion editorial", "가죽 패션 화보"),
        ("니트", "knitwear editorial", "니트 화보"),
        ("데님", "denim editorial", "데님 화보"),
    ],
    "뷰티": [
        ("메이크업 화보", "beauty editorial makeup", "뷰티 화보"),
        ("윤광 피부", "glossy skin makeup", "윤광 메이크업"),
        ("그래픽 아이라인", "graphic eyeliner", "그래픽 아이라이너"),
        ("헤어 화보", "hair editorial", "헤어 화보"),
    ],
    "잡지": [
        ("보그 화보", "Vogue editorial", "보그 화보"),
        ("보그 코리아", "Vogue Korea editorial", "보그 코리아 화보"),
        ("하퍼스 바자 (브로도비치 시절)", "Brodovitch Harper's Bazaar", "브로도비치 하퍼스 바자"),
        ("아이디 (i-D)", "i-D magazine", "i-D 매거진"),
        ("데이즈드 (Dazed)", "Dazed magazine", "데이즈드 매거진"),
        ("더 페이스 (The Face)", "The Face magazine", "더 페이스 매거진"),
        ("퍼플 (Purple)", "Purple magazine", "퍼플 매거진"),
        ("셀프 서비스 (Self Service)", "Self Service magazine", "셀프 서비스 매거진"),
        ("더블유 (W)", "W magazine editorial", "W 매거진 화보"),
        ("어나더 (AnOther)", "AnOther magazine", "어나더 매거진"),
        ("시스템 (System)", "System magazine", "시스템 매거진"),
    ],
    "무드보드 만들기": [
        ("패션 무드보드", "fashion moodboard", "패션 무드보드"),
        ("무드보드 배치", "moodboard layout", "무드보드 레이아웃"),
        ("콜라주 무드보드", "collage moodboard", "콜라주 무드보드"),
        ("색상 팔레트 무드보드", "color palette moodboard", "컬러 팔레트 무드보드"),
        ("브랜드 무드보드", "brand moodboard fashion", "브랜드 무드보드"),
    ],
}

# (이름, URL 틀: {q}=%20 인코딩, {p}=+ 인코딩, {h}=하이픈 연결, 설명, 검색어 언어)
SITES = [
    ("핀터레스트", "https://www.pinterest.com/search/pins/?q={q}", "무드보드·지면 스크랩", "en"),
    ("비핸스", "https://www.behance.net/search/projects?search={q}", "디자이너 프로젝트·편집 디자인", "en"),
    ("구글 이미지", "https://www.google.com/search?tbm=isch&q={p}", "가장 넓게 찾기", "en"),
    ("빙 이미지", "https://www.bing.com/images/search?q={p}", "구글과 다른 결과", "en"),
    ("네이버 이미지", "https://search.naver.com/search.naver?where=image&query={p}", "국내 잡지·화보 (한국어 검색)", "ko"),
    ("다음 이미지", "https://search.daum.net/search?w=img&q={p}", "국내 결과 (한국어 검색)", "ko"),
    ("텀블러", "https://www.tumblr.com/search/{q}", "잡지 스캔·아카이브 블로그", "en"),
    ("플리커", "https://www.flickr.com/search/?text={p}", "사진가 원본, 라이선스로 거르기 가능", "en"),
    ("언스플래시", "https://unsplash.com/s/photos/{h}", "무료 사진 (언스플래시 라이선스)", "en"),
    ("펙셀스", "https://www.pexels.com/search/{q}/", "무료 사진 (펙셀스 라이선스)", "en"),
    ("보그 닷컴", "https://www.vogue.com/search?q={p}", "보그 기사·화보", "en"),
    ("위키미디어 커먼즈", "https://commons.wikimedia.org/w/index.php?search={p}&title=Special:MediaSearch&type=image",
     "자유 라이선스 이미지", "en"),
    ("구글 아트 앤 컬처", "https://artsandculture.google.com/search?q={p}", "박물관·패션 아카이브", "en"),
    ("유로피아나", "https://www.europeana.eu/en/search?query={p}", "유럽 기관 소장품", "en"),
    ("인터넷 아카이브", "https://archive.org/search?query={p}", "옛 잡지 스캔 많음, 권리 불분명한 것 다수", "en"),
]

HUBS = [
    ("잡지 원본 보기", [
        ("보그 아카이브 (유료)", "https://archive.vogue.com"),
        ("프로퀘스트 보그 아카이브 (도서관)", "https://about.proquest.com/en/products-services/vogue_archive/"),
        ("프로퀘스트 WWD 아카이브 (도서관)", "https://about.proquest.com/en/products-services/www/"),
    ]),
    ("표지·지면 모음", [
        ("커버정키 (잡지 표지)", "https://coverjunkie.com"),
        ("스택 매거진", "https://stackmagazines.com"),
        ("맥컬처 (잡지 문화)", "https://magculture.com"),
        ("폰츠 인 유즈 (쓰인 서체)", "https://fontsinuse.com"),
        ("잇츠 나이스 댓 (디자인 매체)", "https://www.itsnicethat.com"),
    ]),
    ("화보·런웨이", [
        ("보그 런웨이 (컬렉션)", "https://www.vogue.com/fashion-shows"),
        ("모델스닷컴 (화보·크레딧)", "https://models.com"),
        ("쇼스튜디오", "https://www.showstudio.com"),
    ]),
    ("무드보드 모으는 곳", [
        ("아레나 (Are.na)", "https://www.are.na"),
        ("코스모스 (Cosmos)", "https://www.cosmos.so"),
        ("사비 (Savee)", "https://savee.it"),
        ("디자인스퍼레이션", "https://www.designspiration.com"),
    ]),
]

HASHTAGS = ["편집디자인", "잡지디자인", "패션화보", "무드보드", "타이포그래피",
            "editorialdesign", "magazinedesign", "fashioneditorial", "magazinecover", "artdirection"]


def url_for(template: str, keyword: str) -> str:
    return template.format(q=quote(keyword), p=quote_plus(keyword), h=quote(keyword.lower().replace(" ", "-")))


def build() -> str:
    e = html.escape
    sections = []
    for cat, kws in KEYWORDS.items():
        items = []
        for ko, en, ko_q in kws:
            chips = "".join(
                f'<a href="{e(url_for(t, ko_q if lang == "ko" else en))}" target="_blank" rel="noopener">{e(name)}</a>'
                for name, t, _, lang in SITES)
            items.append(f'<li class="kw" data-text="{e(" ".join((cat, ko, en, ko_q)).lower())}">'
                         f'<p class="label"><span class="cat">{e(cat)} /</span> {e(ko)}</p>'
                         f'<p class="q">검색어: {e(en)} · {e(ko_q)}</p>'
                         f'<div class="chips">{chips}</div></li>')
        sections.append(f'<section class="group"><h2>{e(cat)} <span class="n">{len(kws)}</span></h2>'
                        f'<ul class="kws">{"".join(items)}</ul></section>')
    hubs = "".join(f'<div class="hub"><h3>{e(t)}</h3><ul>' + "".join(
        f'<li><a href="{e(u)}" target="_blank" rel="noopener">{e(n)}</a></li>' for n, u in items) + "</ul></div>"
        for t, items in HUBS)
    tags = "".join(f'<a href="https://www.instagram.com/explore/tags/{e(quote(h))}/" target="_blank" rel="noopener">#{e(h)}</a>'
                   for h in HASHTAGS)
    sites = "".join(f"<li><b>{e(n)}</b><span>{e(note)}</span></li>" for n, _, note, _ in SITES)
    n_kw = sum(len(v) for v in KEYWORDS.values())
    return f"""<title>패션 무드보드 색인</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:opsz,wght@6..96,500;6..96,700&family=Nanum+Myeongjo:wght@700;800&family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap">
<style>
/* Layout: a magazine index. Didone masthead, one column of keyword entries, site links as wrapping chips. */
:root{{
  --paper:#fbfbfd; --ink:#16171c; --muted:#62646f; --rule:#dfe0e7; --chip:#eef0f7; --accent:#2340b8;
  --display:"Bodoni Moda","Nanum Myeongjo","AppleMyungjo",Georgia,serif;
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
.q{{margin:0;font-size:12px;color:var(--muted)}}
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
  <p class="stats">패션 잡지 레퍼런스 &middot; 키워드 {n_kw}개 &middot; 사이트 {len(SITES)}곳</p>
  <h1>무드보드 색인</h1>
  <p class="dek">무드보드용 키워드를 <b>분류 / 키워드</b>로 정리했습니다. 사이트 이름을 누르면 그 사이트의 검색 결과가 새 탭에서 열립니다.
  해외 사이트는 영어 검색어로, 네이버와 다음은 한국어 검색어로 찾습니다.</p>
  <label for="f" class="stats">키워드 거르기</label>
  <input id="f" type="search" placeholder="예: 표지, 흑백, 90년대, 보그">
  <p class="empty" id="none" hidden>맞는 키워드가 없습니다.</p>
</header>
{''.join(sections)}
<section class="group"><h2>키워드 없이 둘러볼 곳</h2><div class="hubs">{hubs}</div></section>
<section class="group"><h2>인스타그램 해시태그</h2><div class="tags">{tags}</div></section>
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
    print(f"wrote {out}: 키워드 {n_kw}개 x 사이트 {len(SITES)}곳 = 검색 링크 {n_kw * len(SITES)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
