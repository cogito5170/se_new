"""Design-feature representation with explicit evidence levels.

Every one of the ten features is always present with a status:

    observed    measured from bytes we actually processed (DOM counts, image
                header bytes, decoded pixels, CSS source declarations)
    inferred    derived by a named rule from observed data or from declarations
                (e.g. og:image:width) that we did not measure ourselves
    unverified  not analysed; value is null and `basis` says what is missing

Nothing here renders pages. Features that need a rendered layout (grid,
whitespace, rendered hierarchy) stay `unverified` -- an extension point for
a future screenshot/vision analyser, not something this MVP claims to do.
"""
from __future__ import annotations

import re

from .extract import PageExtract
from .images import aspect_ratio
from .models import DESIGN_FEATURES

SERIF_HINTS = ("serif", "georgia", "times", "garamond", "playfair", "didot", "bodoni", "caslon",
               "baskerville", "merriweather", "lora", "freight", "tiempos", "canela", "cormorant",
               "libre baskerville", "noto serif", "source serif", "domine", "spectral")
SANS_HINTS = ("sans", "helvetica", "arial", "inter", "futura", "roboto", "neue haas", "avenir",
              "gotham", "proxima", "lato", "montserrat", "open sans", "work sans", "akzidenz",
              "univers", "graphik", "system-ui", "-apple-system", "segoe")
MONO_HINTS = ("mono", "courier", "consolas", "menlo")


def _feature(status: str, value=None, method: str | None = None, basis: str | None = None) -> dict:
    return {"status": status, "value": value if status != "unverified" else None,
            "method": method, "basis": basis}


def _claim(feature: str, claim: str, method: str | None) -> dict:
    return {"feature": feature, "claim": claim, "method": method}


def classify_font(name: str) -> str:
    n = name.lower()
    if any(h in n for h in MONO_HINTS):
        return "mono"
    if "sans" in n or any(h in n for h in SANS_HINTS if h != "sans"):
        return "sans"
    if any(h in n for h in SERIF_HINTS):
        return "serif"
    return "unclassified"


def build_features(ex: PageExtract, measured: dict[str, dict] | None = None) -> tuple[dict, dict, str]:
    """Return (visual_features, analysis, analysis_status)."""
    measured = measured or {}
    vf: dict[str, dict] = {}
    an = {"observed": [], "inferred": [], "unverified": []}
    st = ex.stats or {}

    # page_type ---------------------------------------------------------------
    src = ex.field_sources.get("page_type")
    if ex.page_type != "unknown" and src and not src.startswith("rule:"):
        vf["page_type"] = _feature("observed", ex.page_type, f"metadata:{src}",
                                   "declared in page metadata; layout not visually verified")
        an["observed"].append(_claim("page_type", f"page declares type '{ex.page_type}'", src))
    elif ex.page_type != "unknown":
        vf["page_type"] = _feature("inferred", ex.page_type, src, "rule-based (no type declared)")
        an["inferred"].append(_claim("page_type", f"page looks like '{ex.page_type}'", src))
    else:
        vf["page_type"] = _feature("unverified", basis="no page type declared in metadata")

    # text_density --------------------------------------------------------------
    words = st.get("word_count", 0)
    imgs = st.get("content_images", 0)
    wpi = round(words / imgs, 1) if imgs else None
    vf["text_density"] = _feature(
        "observed",
        {"word_count": words, "paragraphs": st.get("paragraphs", 0), "content_images": imgs,
         "words_per_image": wpi},
        "html_text_count", f"visible text counted within <{st.get('text_scope', 'body')}>")
    an["observed"].append(_claim("text_density", f"{words} words, {imgs} content images",
                                 "html_text_count"))
    if words < 300 or (wpi is not None and wpi < 150):
        label = "low"
    elif words > 1500 or (wpi is not None and wpi > 800):
        label = "high"
    else:
        label = "medium"
    an["inferred"].append(_claim("text_density", f"{label} text density",
                                 "rule:words<300|wpi<150=low; words>1500|wpi>800=high"))

    # editorial_structure ---------------------------------------------------------
    heads = st.get("headings", {})
    structure = {
        "headings": heads, "figures": st.get("figures", 0), "figcaptions": st.get("figcaptions", 0),
        "blockquotes": st.get("blockquotes", 0), "lists": st.get("lists", 0),
        "tables": st.get("tables", 0), "has_byline": bool(ex.authors),
        "has_dek": bool(ex.description), "article_element": st.get("article_element", False),
    }
    vf["editorial_structure"] = _feature("observed", structure, "html_dom_structure",
                                         "element counts from the HTML document")
    an["observed"].append(_claim("editorial_structure",
                                 f"{sum(heads.values())} headings, {structure['figures']} figures, "
                                 f"{structure['blockquotes']} blockquotes", "html_dom_structure"))
    if words > 1500 and heads.get("h2", 0) >= 2:
        an["inferred"].append(_claim("editorial_structure", "long-form feature",
                                     "rule:words>1500 and h2>=2"))
    if imgs >= 5 and words < 600:
        an["inferred"].append(_claim("editorial_structure", "photo-led story",
                                     "rule:content_images>=5 and words<600"))
    if structure["blockquotes"]:
        an["inferred"].append(_claim("editorial_structure", "pull quotes present",
                                     "rule:blockquote>=1"))

    # visual_hierarchy -----------------------------------------------------------
    if sum(heads.values()):
        vf["visual_hierarchy"] = _feature(
            "inferred", {"heading_levels": heads,
                         "first_headings": [f"{t}: {x}" for t, x in st.get("heading_texts", [])[:5]]},
            "dom_heading_outline",
            "document heading outline only; rendered type sizes and weights were not measured")
        an["inferred"].append(_claim("visual_hierarchy",
                                     f"{heads.get('h1', 0)} h1 / {heads.get('h2', 0)} h2 outline",
                                     "dom_heading_outline"))
    else:
        vf["visual_hierarchy"] = _feature("unverified", basis="no headings found; page not rendered")
    an["unverified"].append(_claim("visual_hierarchy", "rendered visual hierarchy", None))

    # grid_structure / whitespace -------------------------------------------------
    hint = f"; CSS class hints: {', '.join(ex.css_class_hints[:8])}" if ex.css_class_hints else ""
    vf["grid_structure"] = _feature("unverified", basis="requires rendered layout analysis "
                                                         "(not implemented in this MVP)" + hint)
    an["unverified"].append(_claim("grid_structure", "grid structure", None))
    vf["whitespace"] = _feature("unverified", basis="requires rendered layout analysis "
                                                     "(not implemented in this MVP)")
    an["unverified"].append(_claim("whitespace", "whitespace", None))

    # typography -------------------------------------------------------------------
    if ex.declared_fonts:
        fonts = ex.declared_fonts[:10]
        vf["typography"] = _feature("observed", {"declared_font_families": fonts},
                                    "css_source_font_family",
                                    "font families declared in CSS source; rendering not verified")
        an["observed"].append(_claim("typography", "declares " + ", ".join(fonts[:4]),
                                     "css_source_font_family"))
        classes = [classify_font(f) for f in fonts]
        named = [c for c in classes if c != "unclassified"]
        if named:
            lead = max(set(named), key=named.count)
            an["inferred"].append(_claim("typography", f"{lead} typography declared",
                                         "rule:font-name lookup"))
    else:
        vf["typography"] = _feature("unverified", basis="no font-family declarations found in "
                                                         "inline CSS or font links")
    an["unverified"].append(_claim("typography", "rendered typography", None))

    # image_composition -----------------------------------------------------------
    content = [i for i in ex.images if i.position is not None]
    if ex.images:
        comp = {
            "content_images": len(content),
            "metadata_images": len([i for i in ex.images if i.position is None]),
            "captioned_images": len([i for i in ex.images if i.caption]),
            "images_in_figures": len([i for i in content if i.in_figure]),
            "image_before_first_paragraph": st.get("image_before_first_paragraph", False),
        }
        vf["image_composition"] = _feature("observed", comp, "html_dom_images",
                                           "image elements and their position in the document")
        an["observed"].append(_claim("image_composition",
                                     f"{comp['content_images']} content images, "
                                     f"{comp['captioned_images']} captioned", "html_dom_images"))
        if imgs and wpi is not None and wpi < 150:
            an["inferred"].append(_claim("image_composition", "image-led layout",
                                         "rule:words_per_image<150"))
    else:
        vf["image_composition"] = _feature("unverified", basis="no images found in the document")
    an["unverified"].append(_claim("image_composition",
                                   "in-image composition (subject placement, cropping)", None))

    # aspect_ratio -------------------------------------------------------------------
    primary = next((i for i in ex.images if i.role == "primary"), ex.images[0] if ex.images else None)
    m = measured.get(primary.url) if primary else None
    if primary and m and m.get("width"):
        ar = aspect_ratio(m["width"], m["height"])
        method = "image_header_bytes" if m.get("source") == "image_header" else "image_decoded"
        vf["aspect_ratio"] = _feature("observed", {"primary": ar, "measured_images": len(measured)},
                                      method, "measured from the primary image's bytes")
        an["observed"].append(_claim("aspect_ratio", f"primary image {ar['width']}x{ar['height']} "
                                                     f"({ar['orientation']})", method))
        if st.get("image_before_first_paragraph") and ar["orientation"] == "landscape":
            an["inferred"].append(_claim("image_composition", "hero image likely",
                                         "rule:landscape primary image before first paragraph"))
    elif primary and primary.width and primary.height:
        ar = aspect_ratio(primary.width, primary.height)
        vf["aspect_ratio"] = _feature("inferred", {"primary": ar, "measured_images": 0},
                                      f"declared_dimensions:{primary.role}",
                                      "dimensions declared in markup; image bytes not measured")
        an["inferred"].append(_claim("aspect_ratio", f"primary image declared {ar['orientation']}",
                                     f"declared_dimensions:{primary.role}"))
    else:
        vf["aspect_ratio"] = _feature("unverified", basis="no image dimensions declared or measured")

    # dominant_colors ------------------------------------------------------------------
    colors = m.get("colors") if m else None
    if colors:
        vf["dominant_colors"] = _feature("observed", {"primary": colors}, "pillow_quantize_64px",
                                         "pixels of the primary image were decoded")
        an["observed"].append(_claim("dominant_colors", "primary image palette "
                                     + " ".join(c["hex"] for c in colors), "pillow_quantize_64px"))
    else:
        basis = "image pixels not analysed (needs MAGREF_IMAGE_MODE=colors and Pillow)"
        if ex.theme_color:
            basis += f"; page declares theme-color {ex.theme_color} (not an image measurement)"
        vf["dominant_colors"] = _feature("unverified", basis=basis)
        an["unverified"].append(_claim("dominant_colors", "dominant colours", None))

    assert set(vf) == set(DESIGN_FEATURES)
    ordered = {name: vf[name] for name in DESIGN_FEATURES}
    return ordered, an, "partial"


# --------------------------------------------------------------------------- image types

TYPE_RULES = [
    ("cover", re.compile(r"\b(cover|covers|front[- ]page)\b|표지", re.I)),
    ("interior_page", re.compile(r"\b(spread|spreads|layout|interior|inside pages?|page \d+)\b|펼침|내지", re.I)),
    ("portrait", re.compile(r"\b(portrait|headshot|profile photo)\b|인물", re.I)),
    ("product_photo", re.compile(r"\b(product|still[- ]life|packshot|handbag|sneaker|perfume|watch|jewel\w*)\b", re.I)),
    ("editorial_photo", re.compile(r"\b(editorial|fashion|runway|lookbook|campaign|shoot|look \d+)\b|화보", re.I)),
]
IMAGE_TYPES = ("cover", "interior_page", "editorial_photo", "portrait", "product_photo", "other")


def classify_image_type(*, declared: str | None = None, alt: str | None = None,
                        caption: str | None = None, title: str | None = None,
                        url: str | None = None, page_type: str | None = None) -> tuple[str, str, str | None, str]:
    """Return (type, status, method, basis). Declared types are 'observed'; rules give 'inferred'."""
    if declared:
        d = declared.strip().lower().replace(" ", "_").replace("-", "_")
        if d in IMAGE_TYPES:
            return d, "observed", "source_declared_type", f"source declares type '{declared}'"
    fields = (("alt text", alt), ("caption", caption), ("page title", title),
              ("file path", re.sub(r"[-_/.]", " ", url.split("?")[0]) if url else None))
    for image_type, rx in TYPE_RULES:
        for label, text in fields:
            if text and (match := rx.search(text)):
                return image_type, "inferred", "keyword_rule", f"matched '{match.group(0)}' in {label}"
    if page_type == "product":
        return "product_photo", "inferred", "page_type_rule", "page declares Product"
    return "other", "unverified", None, "no type evidence"
