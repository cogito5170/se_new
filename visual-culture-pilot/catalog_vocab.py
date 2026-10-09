"""Controlled vocabulary for the magazine catalogue: (Korean term, English term) per component.

A tag that is not listed here is rejected by the builder, so descriptions stay in professional
terminology instead of ad-hoc paraphrase. Add a term here before using it.
"""
from __future__ import annotations

LAYOUT = [
    ("풀블리드", "full-bleed"), ("마진 프레임", "margin frame"), ("모듈러 그리드", "modular grid"),
    ("컬럼 그리드", "column grid"), ("단일 컬럼", "single column"), ("비대칭 레이아웃", "asymmetric layout"),
    ("대칭 레이아웃", "symmetrical layout"), ("중앙 축 정렬", "centred axis"), ("좌측 정렬", "flush left"),
    ("우측 정렬", "flush right"), ("화이트 스페이스", "white space"), ("마스트헤드 상단 배치", "masthead at top"),
    ("마스트헤드 오버랩", "masthead overlap"), ("커버라인", "cover lines"), ("스프레드", "spread"),
    ("거터 가로지르기", "across the gutter"), ("인셋 이미지", "inset image"), ("보더 프레임", "border frame"),
    ("패널 분할", "panel division"), ("텍스트 오버레이", "text overlay"), ("캡션 배치", "caption placement"),
    ("장식 테두리", "ornamental border"), ("비네트", "vignette"), ("대각선 구도", "diagonal composition"),
    ("삼분할 구도", "rule of thirds"), ("Z 패턴", "Z-pattern"), ("여백 하단 배치", "bottom margin weight"),
]

TYPOGRAPHY = [
    ("디돈 세리프", "Didone serif"), ("트랜지셔널 세리프", "transitional serif"), ("올드스타일 세리프", "old-style serif"),
    ("슬랩 세리프", "slab serif"), ("그로테스크 산세리프", "grotesque sans"), ("지오메트릭 산세리프", "geometric sans"),
    ("휴머니스트 산세리프", "humanist sans"), ("스크립트", "script"), ("블랙레터", "blackletter"),
    ("아르누보 디스플레이", "Art Nouveau display"), ("아르데코 디스플레이", "Art Deco display"),
    ("핸드레터링", "hand lettering"), ("올캡스", "all caps"), ("스몰캡스", "small caps"), ("이탤릭", "italic"),
    ("넓은 트래킹", "wide tracking"), ("좁은 트래킹", "tight tracking"), ("좁은 레딩", "tight leading"),
    ("고대비 획", "high stroke contrast"), ("타이포그래피 위계", "typographic hierarchy"),
    ("캡션 타이포그래피", "caption typography"), ("텍스트 없음", "no text"),
]

IMAGE = [
    ("패션 플레이트", "fashion plate"), ("포슈아르", "pochoir"), ("석판화", "lithograph"), ("에칭·인그레이빙", "etching / engraving"),
    ("일러스트레이션", "illustration"), ("사진", "photograph"), ("흑백 사진", "monochrome photograph"),
    ("컬러 사진", "colour photograph"), ("스튜디오", "studio"), ("로케이션", "location"),
    ("전신 숏", "full-length shot"), ("미디엄 숏", "medium shot"), ("클로즈업", "close-up"),
    ("단독 인물", "single figure"), ("그룹 구성", "group composition"), ("프로필 포즈", "profile pose"),
    ("정면 포즈", "frontal pose"), ("뒷모습", "back view"), ("하드 라이트", "hard light"), ("소프트 라이트", "soft light"),
    ("실루엣 강조", "silhouette emphasis"), ("단색 배경", "plain background"), ("패턴 배경", "patterned background"),
    ("장식적 배경", "decorative background"), ("실내 장면", "interior scene"), ("평면적 원근", "flattened perspective"),
    ("콜라주", "collage"), ("듀오톤", "duotone"), ("하프톤", "halftone"), ("그레인", "grain"), ("컷아웃", "cut-out"),
]

COLOUR = [  # optional manual tags; the measured values are added automatically
    ("제한 팔레트", "limited palette"), ("스폿 컬러", "spot colour"), ("원색 액센트", "primary accent"),
    ("파스텔", "pastel"), ("어스톤", "earth tones"), ("메탈릭", "metallic"), ("톤온톤", "tone-on-tone"),
]

COMPONENTS = {"layout": LAYOUT, "typography": TYPOGRAPHY, "image": IMAGE, "colour_tags": COLOUR}
COMPONENT_LABEL = {"layout": "레이아웃", "typography": "타이포그래피", "image": "이미지", "colour_tags": "색상"}
ENGLISH = {ko: en for terms in COMPONENTS.values() for ko, en in terms}

RIGHTS = {
    "public_domain_cc0": "퍼블릭 도메인 (기관 Open Access, CC0)",
    "licensed_access_personal_reference": "라이선스 열람본, 개인 참고용 (재배포 금지)",
    "own_scan_personal_reference": "소장본 스캔, 개인 참고용 (재배포 금지)",
    "third_party_unverified": "출처 미확인, 개인 참고용 (재배포 금지)",
}
PUBLIC_RIGHTS = {"public_domain_cc0"}


def unknown_tags(component: str, tags) -> "list[str]":
    allowed = {ko for ko, _ in COMPONENTS[component]}
    return [t for t in tags if t not in allowed]
