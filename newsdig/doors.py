"""**문 목록.** 회차마다 두드릴 곳을 코드가 정한다 -- 모델이 고르지 않는다.

dig/search.py 의 규율을 그대로 옮겼다: 문은 박고(틀), 뜻은 안 박는다.

## 실측 2026-10-12 (Haiku 재현 1회차) -- 문의 절반이 막혔다

    Google News RSS 14곳   robots.txt 로 WebFetch 거절 (ROBOTS_DISALLOWED) -> 뺐다
    wttr.in                robots.txt 거절 -> Open-Meteo API 로 바꿨다
    GDELT 비영어 쿼리       주소가 길어 프록시가 403 (CJK 를 퍼센트 인코딩하면 세 배) ->
                           영어 키워드 + sourcelang 로 바꿨다. GDELT 는 65개 언어를 영어로
                           옮긴 색인을 갖고 있어 영어로 물어도 그 언어 기사가 나온다
    GDELT 예술 쿼리         SERVER_ERROR -> 키워드를 줄였다
    HN points>80 날짜순     2주 묵은 것이 나왔다(점수 조건이 최근 것을 걸러 냄) -> 시각 조건을 박았다
    Wikipedia 현재사건      404 -> 뺐다
    GitHub Trending        날짜가 없어 후보가 못 된다 -> 뺐다

그리고 **날짜 있는 후보가 전부 36시간 밖**이었다. 예술 매체는 주간지 박자로 올린다.
그래서 갈래마다 신선도 창을 따로 둔다(gate.WINDOW). 피드는 HTML 첫 화면 대신 RSS 를
연다 -- RSS 는 글마다 pubDate 를 준다.
"""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

GDELT_LANGS = ("", "jpn", "chi", "ger", "fre", "spa", "kor")
TECH_Q = "(AI OR semiconductor OR robotics)"
ART_Q = '("media art" OR "digital art")'

FEEDS = [  # (이름, 주소, 갈래)
    ("theverge", "https://www.theverge.com/rss/index.xml", "tech"),
    ("arstechnica", "https://feeds.arstechnica.com/arstechnica/technology-lab", "tech"),
    ("techcrunch", "https://techcrunch.com/feed/", "tech"),
    ("restofworld", "https://restofworld.org/feed/latest/", "tech"),
    ("theregister", "https://www.theregister.com/headlines.atom", "tech"),
    ("ieee-spectrum", "https://spectrum.ieee.org/feeds/feed.rss", "tech"),
    ("itmedia", "https://rss.itmedia.co.jp/rss/2.0/news_bursts.xml", "tech"),
    ("heise", "https://www.heise.de/rss/heise-atom.xml", "tech"),
    ("etnews", "https://rss.etnews.com/Section901.xml", "tech"),
    ("technode", "https://technode.com/feed/", "tech"),
    ("can", "https://www.creativeapplications.net/feed/", "techart"),
    ("dezeen-tech", "https://www.dezeen.com/technology/feed/", "techart"),
    ("designboom-tech", "https://www.designboom.com/technology/feed/", "techart"),
    ("cdm", "https://cdm.link/feed/", "techart"),
    ("colossal", "https://www.thisiscolossal.com/feed/", "techart"),
    ("hyperallergic", "https://hyperallergic.com/feed/", "techart"),
    ("spoon-tamago", "https://www.spoon-tamago.com/feed/", "techart"),
    ("rhizome", "https://rhizome.org/editorial/", "techart"),
]
SEARCHES = [  # (갈래, 말) -- 날짜는 회차가 붙인다. 검색 결과에는 날짜가 없을 수 있다
    ("tech", "AI chip news"), ("tech", "robotics drone news"), ("tech", "open source release"),
    ("tech", "cybersecurity breach"), ("tech", "space launch satellite"),
    ("tech", "半導体 ニュース"), ("tech", "人工智能 新闻"), ("tech", "AI 반도체 뉴스"),
    ("techart", "media art exhibition opens"), ("techart", "generative art AI artist"),
    ("techart", "interactive installation"), ("techart", "creative coding"),
    ("techart", "sound art festival"), ("techart", "メディアアート 展示"),
    ("techart", "数字艺术 展览"), ("techart", "미디어아트 전시"),
]


def gdelt(q: str, lang: str, span: str) -> str:
    query = f"{q} sourcelang:{lang}" if lang else q
    return ("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode({
        "query": query, "mode": "artlist", "maxrecords": "25", "timespan": span, "format": "json"}))


def build(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    날 = now.strftime("%Y-%m-%d")
    day_ago = int(now.timestamp()) - 86400
    out: list[dict] = []

    def add(kind, name, target, section="mixed"):
        out.append({"id": f"D{len(out) + 1:02d}", "kind": kind, "name": name,
                    "target": target, "section": section})

    for lang in GDELT_LANGS:
        add("fetch", f"gdelt-tech-{lang or 'all'}", gdelt(TECH_Q, lang, "24h"), "tech")
    for lang in ("", "jpn", "ger", "fre"):
        add("fetch", f"gdelt-art-{lang or 'all'}", gdelt(ART_Q, lang, "3d"), "techart")
    add("fetch", "hn", "https://hn.algolia.com/api/v1/search?tags=story&numericFilters="
        + urllib.parse.quote(f"created_at_i>{day_ago},points>40") + "&hitsPerPage=30", "tech")
    add("fetch", "arxiv", "https://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.RO+OR+cat:cs.GR"
        "+OR+cat:cs.HC+OR+cat:cs.SD&sortBy=submittedDate&max_results=25", "mixed")
    for name, url, sec in FEEDS:
        add("fetch", name, url, sec)
    for sec, q in SEARCHES:
        add("search", f"search-{sec}", f"{q} {날}", sec)
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(build(), ensure_ascii=False, indent=1))
