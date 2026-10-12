"""**문 목록.** 회차마다 두드릴 곳을 코드가 정한다 -- 모델이 고르지 않는다.

dig/search.py 의 규율을 그대로 옮겼다: 문은 박고(틀), 뜻은 안 박는다. 어느 결과가
중요한지는 여기서 안 정한다. 다만 **빠뜨리지 않게** 목록을 코드로 내놓는다 -- 긴 지시문을
가벼운 모델이 다 기억하리라 믿지 않는다.

문의 종류:
    fetch   WebFetch 로 그 주소를 연다
    search  WebSearch 로 그 말을 찾는다
"""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

# ── 갈래별 검색어. 언어마다 직접 옮겨 둔다(모델 번역에 맡기면 회차마다 흔들린다) ──
TECH = {
    "english": '("artificial intelligence" OR semiconductor OR robotics OR "open source" OR chip)',
    "japanese": "(人工知能 OR 半導体 OR ロボット)",
    "chinese": "(人工智能 OR 半导体 OR 机器人 OR 芯片)",
    "german": "(\"künstliche Intelligenz\" OR Halbleiter OR Robotik)",
    "french": "(\"intelligence artificielle\" OR semi-conducteurs OR robotique)",
    "spanish": "(\"inteligencia artificial\" OR semiconductores OR robótica)",
}
ART = {
    "english": '("media art" OR "generative art" OR "interactive installation" OR "creative coding" OR "digital art")',
    "japanese": "(メディアアート OR ジェネラティブアート OR インスタレーション)",
    "chinese": "(新媒体艺术 OR 生成艺术 OR 数字艺术)",
    "german": "(Medienkunst OR \"generative Kunst\" OR \"digitale Kunst\")",
    "french": "(\"art numérique\" OR \"art génératif\" OR \"installation interactive\")",
    "spanish": "(\"arte digital\" OR \"arte generativo\" OR \"instalación interactiva\")",
}
GNEWS = [  # (gl, hl, 기술 검색어, 예술 검색어 또는 None)
    ("US", "en", "AI OR semiconductor OR robotics", "media art OR generative art"),
    ("GB", "en", "AI OR chips OR robotics", None),
    ("JP", "ja", "AI OR 半導体 OR ロボット", "メディアアート"),
    ("TW", "zh-TW", "AI OR 半導體 OR 機器人", None),
    ("DE", "de", "KI OR Halbleiter OR Robotik", "Medienkunst OR digitale Kunst"),
    ("FR", "fr", "IA OR semi-conducteurs OR robotique", "art numérique"),
    ("IN", "en", "AI OR semiconductor OR startup", None),
    ("BR", "pt-BR", "IA OR semicondutores OR robótica", None),
    ("KR", "ko", "AI OR 반도체 OR 로봇", "미디어아트"),
]
FEEDS = [
    ("hn", "https://hn.algolia.com/api/v1/search_by_date?tags=story&numericFilters=points>80"),
    ("arxiv", "https://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.RO+OR+cat:cs.AR"
              "+OR+cat:cs.GR+OR+cat:cs.HC+OR+cat:cs.SD&sortBy=submittedDate&max_results=40"),
    ("hf-papers", "https://huggingface.co/papers"),
    ("gh-trending", "https://github.com/trending"),
    ("lobsters", "https://lobste.rs/hottest.json"),
    ("wiki-events", "https://en.wikipedia.org/wiki/Portal:Current_events"),
    ("can", "https://www.creativeapplications.net/"),
    ("designboom", "https://www.designboom.com/technology/"),
    ("dezeen", "https://www.dezeen.com/technology/"),
    ("cdm", "https://cdm.link/"),
    ("ars-electronica", "https://ars.electronica.art/news/en/"),
    ("rhizome", "https://rhizome.org/editorial/"),
    ("spoon-tamago", "https://www.spoon-tamago.com/"),
    ("stirworld", "https://www.stirworld.com/see-features"),
]
SEARCHES = [  # (갈래, 말) -- 날짜는 회차가 붙인다
    ("tech", "AI chip news"), ("tech", "robotics drone news"), ("tech", "open source release news"),
    ("tech", "cybersecurity breach news"), ("tech", "space launch satellite news"),
    ("tech", "半導体 ニュース"), ("tech", "人工智能 新闻"), ("tech", "AI 반도체 뉴스"),
    ("techart", "media art exhibition"), ("techart", "generative art AI artist"),
    ("techart", "interactive installation opening"), ("techart", "creative coding new work"),
    ("techart", "sound art festival"), ("techart", "メディアアート 展示"),
    ("techart", "新媒体艺术 展览"), ("techart", "미디어아트 전시"),
]


def gdelt(q: str, lang: str, span: str) -> str:
    query = q if lang == "english" else f"{q} sourcelang:{lang}"
    return ("https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode({
        "query": query, "mode": "artlist", "maxrecords": "40", "timespan": span,
        "sort": "hybridrel", "format": "json"}))


def gnews(q: str, gl: str, hl: str) -> str:
    return ("https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": f"{q} when:12h", "hl": hl, "gl": gl, "ceid": f"{gl}:{hl.split('-')[0] if hl == 'pt-BR' else hl}"}))


def build(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    날 = now.strftime("%Y-%m-%d")
    out: list[dict] = []

    def add(kind, name, target, section="mixed"):
        out.append({"id": f"D{len(out) + 1:02d}", "kind": kind, "name": name,
                    "target": target, "section": section})

    for lang, q in TECH.items():
        add("fetch", f"gdelt-tech-{lang}", gdelt(q, lang, "12h"), "tech")
    for lang, q in ART.items():
        add("fetch", f"gdelt-art-{lang}", gdelt(q, lang, "24h"), "techart")
    for gl, hl, tq, aq in GNEWS:
        add("fetch", f"gnews-{gl}-tech", gnews(tq, gl, hl), "tech")
        if aq:
            add("fetch", f"gnews-{gl}-art", gnews(aq, gl, hl), "techart")
    for name, url in FEEDS:
        add("fetch", name, url)
    for sec, q in SEARCHES:
        add("search", f"search-{sec}", f"{q} {날}", sec)
    add("fetch", "weather", "https://wttr.in/Seoul?format=j1", "weather")
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(build(), ensure_ascii=False, indent=1))
