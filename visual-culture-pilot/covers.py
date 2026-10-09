"""Cover drawings for the design catalogue: one small SVG per keyword.

Each cover is drawn from simple shapes and type so it is original, needs no network, and passes the
page's content policy (no external images). Covers depict the idea of a keyword; they are not
reproductions of anyone's work.
"""
from __future__ import annotations

import html
import math

W, H = 160, 200
PAPER, BLOCK, INK, ACCENT = "#f4f5f8", "#c9cdd8", "#1d1f27", "#2340b8"


def _svg(body: str, bg: str, label: str) -> str:
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(label)}" '
            f'xmlns="http://www.w3.org/2000/svg"><rect width="{W}" height="{H}" fill="{bg}"/>{body}</svg>')


def r(x, y, w, h, fill=BLOCK, rx=0, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" {extra}/>'


def c(cx, cy, rr, fill=INK, extra=""):
    return f'<circle cx="{cx}" cy="{cy}" r="{rr}" fill="{fill}" {extra}/>'


def ln(x1, y1, x2, y2, stroke=INK, w=1, extra=""):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{w}" {extra}/>'


def t(x, y, s, size=14, fill=INK, family="sans-serif", weight=400, anchor="start", extra=""):
    fam = html.escape(family, quote=True)
    return (f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}" {extra}>{html.escape(s)}</text>')


def lines(x, y, w, n, gap=6, fill=INK, h=2, last=0.6):
    out = "".join(r(x, y + i * gap, w, h, fill) for i in range(n - 1))
    return out + r(x, y + (n - 1) * gap, w * last, h, fill)


# ---------------------------------------------------------------- design styles

def style(name: str):
    S = {
        "swiss": ("#efefef", "".join(ln(20 + i * 30, 0, 20 + i * 30, H, "#d6d6d6") for i in range(5))
                  + c(110, 70, 34, "#e2231a") + t(18, 150, "Neue", 30, INK, "Helvetica, Arial, sans-serif", 700)
                  + t(18, 178, "Grafik", 30, INK, "Helvetica, Arial, sans-serif", 700)),
        "bauhaus": ("#ece6d8", c(52, 60, 32, "#f2b705") + r(86, 30, 50, 50, "#d62828")
                    + '<polygon points="30,170 80,95 130,170" fill="#1d4e9e"/>' + r(20, 182, 120, 6, INK)),
        "constructivism": ("#e9e1d3", '<polygon points="0,150 160,40 160,80 0,190" fill="#c8102e"/>'
                           + c(48, 62, 26, INK) + t(150, 186, "!", 60, INK, "Impact, sans-serif", 700, "end")),
        "deco": ("#121212", "".join(f'<path d="M20 160 A60 60 0 0 1 140 160" fill="none" stroke="#c9a54c" '
                                    f'stroke-width="2" transform="translate(0,{-i*14}) scale(1)"/>' for i in range(5))
                 + "".join(ln(80, 160, 80 + dx, 40, "#c9a54c", 1.2) for dx in (-60, -30, 0, 30, 60))
                 + r(20, 170, 120, 3, "#c9a54c")),
        "psychedelic": ("#ff7a00", "".join(c(80, 100, 90 - i * 14, col) for i, col in
                                           enumerate(["#7b2cbf", "#ff006e", "#ffbe0b", "#3a86ff", "#06d6a0", "#ff006e"]))),
        "memphis": ("#ffffff", '<path d="M15 40 q10 -14 20 0 t20 0 t20 0" fill="none" stroke="#ff4f9a" stroke-width="5" '
                    'stroke-linecap="round"/>' + '<polygon points="110,30 140,80 80,80" fill="#00b4a6"/>'
                    + c(45, 120, 22, "#ffd23f") + r(90, 110, 50, 20, INK, extra='transform="rotate(-15 115 120)"')
                    + "".join(c(20 + (i * 37) % 130, 160 + (i * 13) % 30, 3, INK) for i in range(9))),
        "newwave": ("#e8e8e8", r(20, 30, 90, 90, "#ff2e63", extra='opacity="0.85"')
                    + r(55, 70, 85, 85, "#08d9d6", extra='opacity="0.85"')
                    + t(18, 182, "NEW/WAVE", 22, INK, "Courier New, monospace", 700)),
        "brutal": ("#ffffff", r(12, 12, 136, 176, "none", extra=f'stroke="{INK}" stroke-width="4"')
                   + t(20, 48, "INDEX", 28, INK, "Courier New, monospace", 700)
                   + lines(20, 64, 110, 6, 9, INK, 3) + t(20, 170, "link", 14, "#0000ee", "Times New Roman, serif",
                                                          400, extra='text-decoration="underline"')),
        "y2k": ("#cfe8ff", '<defs><radialGradient id="y2k" cx="35%" cy="30%"><stop offset="0" stop-color="#fff"/>'
                '<stop offset=".5" stop-color="#b9c3d6"/><stop offset="1" stop-color="#6b7a99"/></radialGradient></defs>'
                + '<ellipse cx="80" cy="95" rx="55" ry="45" fill="url(#y2k)"/>'
                + "".join(f'<path d="M{x} {y} l3 9 9 3 -9 3 -3 9 -3 -9 -9 -3 9 -3z" fill="#ff5fd2"/>'
                          for x, y in ((30, 30), (130, 150), (125, 40)))),
        "gradient": ("#000", '<defs><linearGradient id="gr" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff5f6d"/>'
                     '<stop offset=".5" stop-color="#ffc371"/><stop offset="1" stop-color="#2ec4b6"/></linearGradient></defs>'
                     + r(0, 0, W, H, "url(#gr)")),
        "3d": ("#e9ecf3", '<defs><radialGradient id="sp" cx="35%" cy="35%"><stop offset="0" stop-color="#ffffff"/>'
               '<stop offset="1" stop-color="#3a5bd9"/></radialGradient></defs>'
               + '<ellipse cx="85" cy="165" rx="45" ry="9" fill="#00000022"/>' + c(80, 100, 45, "url(#sp)")),
        "chrome": ("#111", '<defs><linearGradient id="ch" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff"/>'
                   '<stop offset=".45" stop-color="#8a8f99"/><stop offset=".55" stop-color="#2b2e35"/>'
                   '<stop offset="1" stop-color="#e3e6ec"/></linearGradient></defs>'
                   + t(80, 112, "CHROME", 34, "url(#ch)", "Arial Black, Arial, sans-serif", 900, "middle")),
        "grain": ("#2b2d42", '<defs><filter id="gn"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2"/>'
                  '<feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .35 0"/></filter></defs>'
                  + c(80, 90, 50, "#ef8354") + r(0, 0, W, H, "#fff", extra='filter="url(#gn)"')),
        "handdrawn": ("#fffdf7", '<path d="M30 140 C40 60 70 50 80 100 S120 150 130 60" fill="none" stroke="#1d1f27" '
                      'stroke-width="3" stroke-linecap="round"/>' + '<path d="M40 40 q5 -8 10 0 q5 8 10 0" fill="none" '
                      'stroke="#e76f51" stroke-width="3" stroke-linecap="round"/>' + c(120, 160, 10, "none",
                      'stroke="#2a9d8f" stroke-width="3"')),
        "collage": ("#e9e4dc", r(20, 25, 80, 100, "#9aa6b2", extra='transform="rotate(-6 60 75)"')
                    + r(60, 70, 80, 90, "#d4a373", extra='transform="rotate(5 100 115)"')
                    + r(35, 130, 60, 40, "#264653", extra='transform="rotate(-3 65 150)"')
                    + r(48, 18, 40, 10, "#ffffffaa", extra='transform="rotate(-10 68 23)"')),
        "minimal": ("#fafafa", c(80, 92, 6, INK) + ln(40, 150, 120, 150, INK, 0.8)),
        "duotone": ("#1b1f3b", "".join(c(12 + (i % 8) * 20, 12 + (i // 8) * 20, 2 + ((i * 7) % 9), "#ff6fb5")
                                       for i in range(80))),
        "bw": ("#ffffff", r(0, 0, 80, H, INK) + c(80, 100, 40, "#ffffff", f'stroke="{INK}" stroke-width="3"')
               + c(80, 100, 18, INK)),
        "neon": ("#0d0221", '<defs><filter id="gl"><feGaussianBlur stdDeviation="3"/></filter></defs>'
                 + c(80, 95, 45, "none", 'stroke="#ff2a6d" stroke-width="6" filter="url(#gl)"')
                 + c(80, 95, 45, "none", 'stroke="#ffd6e6" stroke-width="2"')
                 + t(80, 175, "OPEN", 22, "#05d9e8", "Arial, sans-serif", 700, "middle")),
        "pastel": ("#fff7f3", r(15, 20, 60, 80, "#ffc8dd", 8) + r(85, 20, 60, 50, "#bde0fe", 8)
                   + r(85, 80, 60, 100, "#cdeac0", 8) + r(15, 110, 60, 70, "#ffe5a3", 8)),
        "primary": ("#ffffff", r(0, 0, 100, 120, "#d62828") + r(100, 120, 60, 80, "#1d4e9e") + r(0, 160, 40, 40, "#f2b705")
                    + ln(100, 0, 100, H, INK, 6) + ln(0, 120, W, 120, INK, 6) + ln(40, 120, 40, H, INK, 6)
                    + ln(0, 160, 100, 160, INK, 6)),
        "palette": ("#ffffff", "".join(r(10 + i * 28, 20, 28, 140, col) for i, col in
                                       enumerate(["#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"]))
                    + t(80, 182, "palette", 14, INK, "Courier New, monospace", 400, "middle")),
        "pattern": ("#ffffff", '<defs><pattern id="pt" width="20" height="20" patternUnits="userSpaceOnUse">'
                    '<circle cx="10" cy="10" r="5" fill="#2340b8"/><rect x="0" y="0" width="4" height="4" fill="#ff7a00"/>'
                    '</pattern></defs>' + r(0, 0, W, H, "url(#pt)")),
        "icons": ("#f4f5f8", "".join(
            (c(40 + (i % 3) * 40, 50 + (i // 3) * 50, 12, "none", f'stroke="{INK}" stroke-width="3"') if i % 3 == 0 else
             r(28 + (i % 3) * 40, 38 + (i // 3) * 50, 24, 24, "none", 4, f'stroke="{INK}" stroke-width="3"') if i % 3 == 1 else
             f'<polygon points="{140},{38 + (i // 3) * 50} {152},{62 + (i // 3) * 50} {128},{62 + (i // 3) * 50}" '
             f'fill="none" stroke="{INK}" stroke-width="3"/>') for i in range(9))),
        "geometric": ("#f4f5f8", c(65, 85, 40, "none", f'stroke="{ACCENT}" stroke-width="3"')
                      + r(70, 70, 60, 60, "none", 0, f'stroke="{INK}" stroke-width="3"')
                      + '<polygon points="40,170 80,110 120,170" fill="none" stroke="#e2231a" stroke-width="3"/>'),
        "lines": ("#ffffff", "".join(ln(0, 10 + i * 12, W, 10 + i * 12 - 30, INK if i % 2 else ACCENT, 4)
                                     for i in range(19))),
        "stickers": ("#f1f1f1", c(55, 60, 32, "#ffd23f", f'stroke="{INK}" stroke-width="3"')
                     + t(55, 66, "NEW", 16, INK, "Arial Black, sans-serif", 900, "middle")
                     + r(70, 100, 75, 40, "#ff4f9a", 20, f'stroke="{INK}" stroke-width="3" transform="rotate(8 107 120)"')
                     + '<path d="M50 140 l8 16 18 3 -13 12 3 18 -16 -9 -16 9 3 -18 -13 -12 18 -3z" fill="#2ec4b6" '
                     f'stroke="{INK}" stroke-width="3"/>'),
    }
    return S[name]


# ---------------------------------------------------------------- layout wireframes

def browser(body):
    return (r(10, 30, 140, 140, "#ffffff", 4, f'stroke="{BLOCK}"') + r(10, 30, 140, 12, "#e4e6ee", 4)
            + c(18, 36, 2, "#ff5f57") + c(25, 36, 2, "#febc2e") + c(32, 36, 2, "#28c840") + body)


def phone(body):
    return r(45, 15, 70, 170, "#ffffff", 12, f'stroke="{INK}" stroke-width="3"') + body


def layout(name: str):
    P = PAPER
    L = {
        "grid": (P, "".join(r(14 + i * 23, 10, 17, 180, "#e2e5ee") for i in range(6)) + r(14, 20, 63, 70)
                 + r(83, 20, 63, 30, ACCENT) + lines(83, 60, 63, 4) + lines(14, 100, 132, 8)),
        "modular": (P, "".join(r(14 + (i % 3) * 46, 14 + (i // 3) * 44, 40, 38, BLOCK if i % 4 else ACCENT)
                               for i in range(12))),
        "asym": (P, r(50, 18, 96, 120) + lines(14, 150, 60, 5) + t(14, 40, "A", 30, INK, "Georgia, serif", 700)),
        "whitespace": (P, r(98, 120, 40, 50) + lines(98, 178, 40, 2)),
        "hierarchy": (P, r(14, 24, 120, 18, INK) + r(14, 52, 90, 8, INK) + lines(14, 72, 132, 12)),
        "align": (P, ln(24, 10, 24, 190, ACCENT, 1, 'stroke-dasharray="3 3"') + r(24, 22, 100, 14, INK)
                  + r(24, 46, 120, 60) + lines(24, 116, 110, 9)),
        "spread": (P, r(6, 40, 74, 120, "#ffffff", 0, f'stroke="{BLOCK}"') + r(80, 40, 74, 120, "#ffffff", 0,
                   f'stroke="{BLOCK}"') + r(6, 40, 74, 120) + r(90, 52, 55, 10, INK) + lines(90, 72, 55, 10)),
        "cover": (P, r(14, 14, 132, 172) + t(80, 46, "MAGAZINE", 22, INK, "Bodoni Moda, Didot, serif", 700, "middle")
                  + lines(22, 140, 50, 3, 7, "#ffffff", 3) + r(22, 162, 70, 6, "#ffffff")),
        "book": (P, r(24, 14, 112, 172, "#ffffff", 0, f'stroke="{BLOCK}"') + lines(38, 34, 84, 18, 7) + t(80, 178, "37", 8, INK,
                 "Georgia, serif", 400, "middle")),
        "columns": (P, r(14, 18, 132, 14, INK) + "".join(lines(14 + i * 46, 44, 40, 18, 7) for i in range(3))),
        "fullbleed": ("#9aa6b2", r(0, 0, W, H, "#9aa6b2") + c(110, 70, 26, "#ffffff55") + r(14, 170, 60, 4, "#ffffff")
                      + r(14, 178, 40, 4, "#ffffff")),
        "brochure": (P, "".join(r(8 + i * 49, 30, 47, 140, "#ffffff", 0, f'stroke="{BLOCK}"') for i in range(3))
                     + r(8, 30, 47, 70) + lines(62, 44, 36, 10) + r(111, 44, 36, 36, ACCENT) + lines(111, 90, 36, 8)),
        "report": (P, r(14, 18, 100, 12, INK) + "".join(r(20 + i * 24, 150 - hh, 16, hh, ACCENT if i == 3 else BLOCK)
                                                        for i, hh in enumerate((40, 60, 52, 90, 70))) + ln(14, 150, 146, 150)
                   + lines(14, 162, 132, 4)),
        "typoposter": ("#f2f2f2", t(80, 150, "Aa", 120, INK, "Helvetica, Arial, sans-serif", 700, "middle")
                       + t(14, 186, "TYPE ONLY", 10, INK, "Helvetica, Arial, sans-serif", 700)),
        "photoposter": (P, r(0, 0, W, 150) + c(60, 70, 30, "#ffffff66") + r(14, 160, 90, 10, INK) + lines(14, 176, 70, 2)),
        "exhibition": ("#ffffff", t(14, 80, "10.24", 44, INK, "Helvetica, Arial, sans-serif", 700)
                       + t(14, 120, "—11.30", 30, ACCENT, "Helvetica, Arial, sans-serif", 700) + lines(14, 150, 100, 4, 7)),
        "festival": ("#ffe14d", t(80, 50, "FEST", 40, INK, "Arial Black, sans-serif", 900, "middle")
                     + "".join(r(20 + (i % 2) * 10, 70 + i * 13, 120 - (i % 3) * 20, 6, INK) for i in range(9))),
        "landing": (P, browser(r(22, 58, 90, 14, INK) + r(22, 78, 70, 6) + r(22, 92, 36, 12, ACCENT, 6)
                               + r(22, 116, 116, 44))),
        "bento": (P, browser(r(18, 50, 60, 54, ACCENT, 4) + r(82, 50, 60, 24, BLOCK, 4) + r(82, 78, 28, 26, BLOCK, 4)
                             + r(114, 78, 28, 26, BLOCK, 4) + r(18, 108, 124, 54, BLOCK, 4))),
        "cards": (P, browser("".join(r(18 + (i % 3) * 42, 52 + (i // 3) * 56, 38, 50, "#ffffff", 3,
                                       f'stroke="{BLOCK}"') + r(18 + (i % 3) * 42, 52 + (i // 3) * 56, 38, 26, BLOCK, 3)
                                     for i in range(6)))),
        "editorialweb": (P, browser(t(22, 76, "Headline", 24, INK, "Georgia, serif", 700) + r(22, 88, 70, 4)
                                    + lines(22, 100, 70, 8) + r(100, 52, 42, 110))),
        "portfolio": (P, browser("".join(r(18 + (i % 3) * 42, 52 + (i // 3) * 38, 38, 34, BLOCK if i % 2 else ACCENT)
                                         for i in range(9)))),
        "mobile": (P, phone(r(55, 32, 50, 30, ACCENT, 6) + "".join(r(55, 70 + i * 20, 50, 14, BLOCK, 4)
                                                                   for i in range(5)))),
        "slides": (P, r(8, 55, 144, 81, "#ffffff", 2, f'stroke="{BLOCK}"') + r(20, 70, 80, 10, INK) + lines(20, 90, 60, 4, 7)
                   + r(108, 70, 34, 50, ACCENT)),
        "feed": (P, "".join(r(14 + (i % 3) * 45, 24 + (i // 3) * 52, 42, 49, BLOCK if i % 2 else "#e7c6a4")
                            for i in range(9))),
        "toc": (P, t(14, 40, "Contents", 20, INK, "Georgia, serif", 700) + "".join(
            t(14, 70 + i * 22, f"{(i + 1) * 12:02d}", 10, INK, "Courier New, monospace", 700) + r(40, 63 + i * 22, 100 - (i % 3) * 18, 4)
            for i in range(6))),
        "carousel": (P, r(40, 40, 96, 96, BLOCK, 4) + r(28, 48, 96, 96, "#e7c6a4", 4) + r(16, 56, 96, 96, "#ffffff", 4,
                     f'stroke="{BLOCK}"') + r(26, 70, 60, 8, INK) + lines(26, 86, 70, 4)
                     + "".join(c(66 + i * 10, 172, 3, INK if i == 0 else BLOCK) for i in range(4))),
    }
    return L[name]


# ---------------------------------------------------------------- font specimens

def font(family: str, sample: str = "가 Aa", note: str = ""):
    body = (t(80, 112, sample, 50 if len(sample) <= 4 else 30, INK, family, 400, "middle")
            + ln(16, 150, 144, 150, BLOCK) + t(16, 170, family.split(",")[0].strip('"'), 11, INK, family)
            + (t(16, 186, note, 9, "#62646f", "sans-serif") if note else ""))
    return ("#ffffff", body)


def fontdemo(name: str):
    D = {
        "pairing": ("#ffffff", t(16, 70, "Headline", 30, INK, "Bodoni Moda, Didot, serif", 700)
                    + lines(16, 90, 128, 8, 8, "#9aa0ad") + t(16, 170, "Bodoni + Inter", 10, INK, "Inter, sans-serif")),
        "variable": ("#ffffff", "".join(t(16 + i * 34, 110, "A", 44, INK, "Inter, sans-serif", w)
                                        for i, w in enumerate((100, 400, 700, 900)))
                     + t(16, 170, "100 → 900", 11, INK, "Inter, sans-serif")),
        "kerning": ("#ffffff", t(80, 115, "AV", 70, INK, "Bodoni Moda, serif", 700, "middle")
                    + ln(70, 135, 90, 135, "#e2231a", 2) + t(80, 160, "← 자간 →", 12, "#e2231a", "sans-serif", 400, "middle")),
        "scale": ("#ffffff", t(16, 70, "Title", 40, INK, "Inter, sans-serif", 700) + t(16, 100, "Subtitle", 20, INK,
                  "Inter, sans-serif", 600) + t(16, 120, "Body text at reading size", 10, INK, "Inter, sans-serif")
                  + t(16, 134, "caption", 8, "#62646f", "Inter, sans-serif")),
        "masthead": ("#ffffff", t(80, 70, "VOGUE", 40, INK, "Bodoni Moda, Didot, serif", 700, "middle", 'letter-spacing="2"')
                     + r(14, 82, 132, 90, BLOCK) + t(18, 186, "masthead", 9, INK, "Courier New, monospace")),
        "big": ("#ffffff", t(-6, 175, "Big", 110, INK, "Helvetica, Arial, sans-serif", 700, extra='letter-spacing="-6"')),
        "experimental": ("#ffffff", "".join(t(30 + (i * 23) % 100, 40 + i * 20, ch, 20 + (i * 7) % 26, INK,
                         "Helvetica, Arial, sans-serif", 700, extra=f'transform="rotate({(i * 37) % 90 - 45} {30 + (i * 23) % 100} {40 + i * 20})"')
                         for i, ch in enumerate("TYPOGRAPH"))),
        "lettering": ("#1d1f27", t(80, 118, "Lettering", 34, "#f4d35e", "Pinyon Script, cursive", 400, "middle")
                      + ln(30, 132, 130, 132, "#f4d35e", 1)),
    }
    return D[name]


# ---------------------------------------------------------------- deliverables

def thing(name: str):
    P = PAPER
    T = {
        "identity": (P, c(48, 60, 22, ACCENT) + r(78, 45, 66, 30, INK) + r(16, 100, 80, 48, "#ffffff", 3, f'stroke="{BLOCK}"')
                     + c(30, 114, 6, ACCENT) + lines(30, 128, 50, 2) + r(102, 100, 42, 80, "#ffffff", 2, f'stroke="{BLOCK}"')
                     + c(112, 112, 4, ACCENT)),
        "logo": ("#ffffff", c(80, 82, 34, INK) + c(80, 82, 14, "#ffffff") + r(46, 140, 68, 10, INK)),
        "wordmark": ("#ffffff", t(80, 110, "brand", 40, INK, "Helvetica, Arial, sans-serif", 700, "middle", 'letter-spacing="-2"')),
        "stationery": (P, r(20, 20, 90, 120, "#ffffff", 0, f'stroke="{BLOCK}"') + c(32, 34, 5, ACCENT) + lines(30, 60, 70, 8)
                       + r(60, 120, 84, 50, "#ffffff", 3, f'stroke="{BLOCK}" transform="rotate(-8 102 145)"')
                       + c(76, 138, 5, ACCENT, 'transform="rotate(-8 102 145)"')),
        "guidelines": (P, r(10, 40, 70, 120, "#ffffff", 0, f'stroke="{BLOCK}"') + r(80, 40, 70, 120, "#ffffff", 0, f'stroke="{BLOCK}"')
                       + c(45, 80, 16, ACCENT) + lines(20, 110, 50, 4) + "".join(r(88 + i * 14, 56, 12, 40, col) for i, col in
                       enumerate((ACCENT, INK, BLOCK, "#e2231a"))) + lines(88, 110, 54, 4)),
        "poster": (P, r(30, 14, 100, 172, "#e2231a") + c(80, 80, 30, "#ffffff") + r(42, 150, 76, 8, "#ffffff") + r(42, 164, 50, 5, "#ffffff")),
        "bookcover": (P, r(40, 20, 90, 160, "#264653") + r(30, 20, 10, 160, "#1b343c") + r(52, 50, 66, 10, "#e9c46a")
                      + r(52, 66, 44, 6, "#e9c46a") + r(52, 150, 40, 5, "#ffffff")),
        "album": (P, c(105, 100, 48, INK) + c(105, 100, 12, "#e2231a") + r(14, 52, 96, 96, "#f4a261")
                  + t(24, 140, "LP", 22, INK, "Arial Black, sans-serif", 900)),
        "magazine": layout("cover"),
        "zine": ("#eeeeee", r(30, 30, 100, 140, "#ffffff", 0, f'stroke="{INK}" stroke-width="2" transform="rotate(-4 80 100)"')
                 + t(44, 78, "ZINE", 30, INK, "Courier New, monospace", 700, extra='transform="rotate(-4 80 100)"')
                 + r(44, 90, 70, 50, INK, extra='transform="rotate(-4 80 100)" opacity=".8"')
                 + r(78, 26, 4, 10, "#9aa0ad") + r(78, 166, 4, 10, "#9aa0ad")),
        "packaging": (P, '<polygon points="40,70 80,50 120,70 80,90" fill="#ffd166"/>'
                      '<polygon points="40,70 80,90 80,160 40,140" fill="#ef476f"/>'
                      '<polygon points="80,90 120,70 120,140 80,160" fill="#d43d61"/>'
                      + t(60, 125, "BOX", 12, "#ffffff", "Arial Black, sans-serif", 900, "middle")),
        "cosmetic": (P, r(40, 60, 34, 110, "#f1c0cb", 6) + r(48, 40, 18, 20, INK, 3) + r(88, 90, 40, 80, "#ffffff", 8,
                     f'stroke="{BLOCK}"') + r(96, 74, 24, 16, "#c9a54c", 3) + lines(46, 120, 22, 3, 6, INK)),
        "merch": (P, '<path d="M40 60 l20 -20 h40 l20 20 -14 14 -6 -6 v90 h-40 v-90 l-6 6z" fill="#ffffff" '
                  f'stroke="{INK}" stroke-width="2"/>' + c(80, 92, 14, ACCENT)),
        "label": (P, r(50, 30, 60, 20, "#9aa0ad", 3) + r(40, 50, 80, 120, "#d9ead3", 14, f'stroke="{BLOCK}"')
                  + r(48, 86, 64, 50, "#ffffff", 2, f'stroke="{INK}"') + t(80, 108, "Label", 14, INK, "Georgia, serif", 700, "middle")
                  + lines(58, 118, 44, 2, 6)),
        "lookbook": (P, r(10, 30, 70, 140, "#ffffff", 0, f'stroke="{BLOCK}"') + r(80, 30, 70, 140, "#ffffff", 0, f'stroke="{BLOCK}"')
                     + c(45, 60, 9, INK) + r(33, 72, 24, 70, INK, 6) + c(115, 60, 9, "#9aa0ad") + r(103, 72, 24, 70, "#9aa0ad", 6)
                     + t(16, 186, "SS26", 9, INK, "Helvetica, sans-serif", 700)),
        "campaign": ("#cfd5df", r(10, 40, 140, 90, "#9aa6b2") + c(60, 80, 12, "#ffffff") + r(52, 92, 16, 38, "#ffffff", 4)
                     + t(140, 122, "NOW", 20, "#ffffff", "Arial Black, sans-serif", 900, "end") + r(78, 130, 4, 50, INK)),
        "fashionweb": (P, browser(r(14, 46, 132, 90, "#9aa6b2") + t(80, 100, "COLLECTION", 14, "#ffffff", "Helvetica, sans-serif",
                       700, "middle") + "".join(r(18 + i * 42, 142, 38, 22, BLOCK) for i in range(3)))),
        "invitation": (P, '<polygon points="20,80 80,120 140,80 140,170 20,170" fill="#e7c6a4"/>'
                       + r(36, 30, 88, 90, "#ffffff", 0, f'stroke="{BLOCK}"') + t(80, 64, "Invitation", 16, INK,
                       "Pinyon Script, cursive", 400, "middle") + lines(54, 80, 52, 3, 7)),
        "website": (P, browser(r(22, 54, 116, 10, INK) + r(22, 72, 116, 50) + lines(22, 132, 116, 4, 7))),
        "app": (P, phone(r(55, 32, 50, 12, INK, 3) + r(55, 52, 50, 50, ACCENT, 6) + lines(55, 112, 50, 6, 8)
                         + r(55, 162, 50, 12, BLOCK, 6))),
        "motion": ("#1d1f27", "".join(r(10 + i * 36, 70, 32, 60, "#2b2e38", 2) + c(26 + i * 36, 100 - i * 8, 8, "#f4d35e")
                                      for i in range(4)) + "".join(r(10 + i * 12, 58, 6, 6, "#555") for i in range(12))
                   + "".join(r(10 + i * 12, 136, 6, 6, "#555") for i in range(12))),
        "social": (P, r(20, 30, 120, 120, "#e7c6a4", 4) + t(80, 100, "POST", 24, INK, "Arial Black, sans-serif", 900, "middle")
                   + '<path d="M30 168 c0 -8 12 -8 12 0 c0 -8 12 -8 12 0 c0 8 -12 14 -12 16 c0 -2 -12 -8 -12 -16z" fill="#e2231a"/>'
                   + lines(64, 164, 70, 2, 7)),
        "exhibitiondesign": (P, '<polygon points="0,40 40,60 40,160 0,190" fill="#e4e6ee"/>'
                             '<polygon points="160,40 120,60 120,160 160,190" fill="#e4e6ee"/>'
                             + r(40, 60, 80, 100, "#ffffff") + r(55, 80, 50, 40, ACCENT) + r(0, 160, W, 40, "#d6d9e2")),
        "store": (P, r(14, 40, 132, 140, "#ffffff", 0, f'stroke="{INK}" stroke-width="2"') + r(14, 40, 132, 26, INK)
                  + t(80, 58, "STORE", 14, "#ffffff", "Helvetica, sans-serif", 700, "middle") + r(26, 80, 50, 90, "#cfe3f1")
                  + r(88, 80, 46, 100, "#e4e6ee")),
        "signage": (P, r(76, 60, 8, 130, INK) + '<polygon points="30,40 120,40 140,60 120,80 30,80" fill="#2a9d8f"/>'
                    + t(70, 66, "GATE 3 →", 14, "#ffffff", "Helvetica, sans-serif", 700, "middle")
                    + '<polygon points="130,100 40,100 20,120 40,140 130,140" fill="#f4a261"/>'
                    + t(80, 126, "← EXIT", 14, INK, "Helvetica, sans-serif", 700, "middle")),
    }
    return T[name]



# ---------------------------------------------------------------- photographs (drawn, not photographed)

def figure(x, y, s=1.0, fill=INK, op=1.0):
    return (f'<g opacity="{op}">' + c(x, y, 9 * s, fill) + r(x - 12 * s, y + 12 * s, 24 * s, 46 * s, fill, 8 * s)
            + r(x - 10 * s, y + 56 * s, 8 * s, 34 * s, fill, 3) + r(x + 2 * s, y + 56 * s, 8 * s, 34 * s, fill, 3) + "</g>")


def photo(name: str):
    G = {
        "studio": ("#d9d9d9", '<path d="M0 120 Q0 150 40 150 H160 V200 H0z" fill="#ececec"/>' + r(118, 20, 30, 40, "#ffffff", 3)
                   + ln(133, 60, 133, 120, "#888") + figure(70, 70, 1.1)),
        "flash": ("#0e0e0e", figure(88, 64, 1.1, "#2a2a2a") + figure(80, 60, 1.1, "#f2f2f2")
                  + c(60, 40, 4, "#ffffff", 'opacity=".9"')),
        "film": ("#111111", r(10, 40, 140, 120, "#777777") + figure(80, 70, 0.9, "#222222")
                 + "".join(r(14 + i * 14, 28, 8, 8, "#dddddd", 1) + r(14 + i * 14, 164, 8, 8, "#dddddd", 1) for i in range(10))
                 + t(150, 190, "400", 9, "#dddddd", "Courier New, monospace", 700, "end")),
        "bwphoto": ("#ffffff", r(0, 0, 80, H, INK) + figure(80, 60, 1.2, "#888888")),
        "stilllife": ("#ececec", r(0, 140, W, 60, "#d4d4d4") + r(40, 70, 26, 74, "#4a4a4a", 6) + r(47, 56, 12, 16, INK, 2)
                      + r(78, 96, 50, 48, "#9a9a9a", 4) + '<path d="M88 96 q15 -26 30 0" fill="none" stroke="#4a4a4a" stroke-width="4"/>'
                      + '<ellipse cx="95" cy="146" rx="60" ry="5" fill="#00000022"/>'),
        "outdoor": ("#e8e8e8", c(120, 45, 18, "#ffffff") + '<path d="M0 130 L50 90 L90 120 L130 80 L160 110 V200 H0z" fill="#9c9c9c"/>'
                    + r(0, 150, W, 50, "#6e6e6e") + figure(55, 95, 0.75)),
        "street": ("#dcdcdc", r(0, 20, 40, 120, "#8a8a8a") + r(44, 50, 36, 90, "#a5a5a5") + r(84, 10, 40, 130, "#7a7a7a")
                   + r(128, 40, 32, 100, "#b0b0b0") + "".join(r(10 + i * 26, 160, 16, 30, "#ffffff") for i in range(6))
                   + r(0, 140, W, 60, "#4a4a4a", extra='opacity=".35"') + figure(100, 112, 0.7)),
        "closeup": ("#cfcfcf", c(80, 120, 80, "#8f8f8f") + c(52, 108, 7, INK) + c(108, 108, 7, INK)
                    + r(66, 150, 28, 6, INK, 3)),
        "fullbody": ("#efefef", r(0, 170, W, 30, "#d9d9d9") + figure(80, 38, 1.4)),
        "motionblur": ("#f2f2f2", "".join(figure(40 + i * 18, 60, 1, INK, 0.15 + i * 0.2) for i in range(5))),
    }
    return G[name]


def treat(name: str):
    T = {
        "halftone": ("#ffffff", "".join(c(8 + (i % 10) * 16, 8 + (i // 10) * 16, 1 + 6.5 * ((i % 10) / 9) * ((i // 10) / 12), INK)
                                        for i in range(130))),
        "cutout": ("#ededed", figure(84, 50, 1.4, "#bdbdbd") + figure(78, 44, 1.4, INK) + r(14, 160, 70, 8, INK)),
        "lineart": ("#ffffff", '<path d="M50 60 q30 -40 60 0 q10 30 -10 50 q20 10 20 60 h-80 q0 -50 20 -60 q-20 -20 -10 -50z" '
                    f'fill="none" stroke="{INK}" stroke-width="2"/>' + c(68, 70, 2, INK) + c(92, 70, 2, INK)
                    + '<path d="M72 90 q8 6 16 0" fill="none" stroke="#1d1f27" stroke-width="2"/>'),
        "flat": ("#f2f2f2", c(80, 80, 50, "#bcbcbc") + r(40, 110, 80, 60, "#6f6f6f", 6) + c(80, 70, 18, INK)
                 + r(20, 170, 120, 8, INK)),
        "riso": ("#f7f3ec", c(70, 90, 40, "#ff48b0", 'style="mix-blend-mode:multiply"')
                 + c(92, 104, 40, "#0078bf", 'style="mix-blend-mode:multiply"') + t(16, 186, "RISO", 12, INK, "Courier New, monospace", 700)),
        "pixel": ("#ffffff", "".join(r(30 + (i % 10) * 10, 40 + (i // 10) * 10, 10, 10, INK) for i in range(100)
                                     if (i % 10 - 4.5) ** 2 + (i // 10 - 4.5) ** 2 < 20 and not (i in (33, 36, 72, 73, 74, 75, 76)))),
    }
    return T[name]


# ---------------------------------------------------------------- colour covers (the only covers kept in colour)

def swatches(cols, labels=True):
    n = len(cols)
    w = (W - 20) / n
    out = "".join(r(10 + i * w, 14, w, 150, col) for i, col in enumerate(cols))
    if labels:  # hex codes written up each swatch, in black or white depending on the swatch's brightness
        for i, col in enumerate(cols):
            rr, gg, bb = (int(col[k:k + 2], 16) for k in (1, 3, 5))
            ink = "#000000" if 0.299 * rr + 0.587 * gg + 0.114 * bb > 150 else "#ffffff"
            x = 10 + i * w + w / 2 + 3
            out += t(x, 158, col.upper().lstrip("#"), 9, ink, "Courier New, monospace", 700, "start",
                     f'transform="rotate(-90 {x:.1f} 158)"')
    return out


def colour(name: str):
    P = "#ffffff"
    C = {
        "bw": (P, r(10, 14, 70, 150, "#000000") + r(80, 14, 70, 150, "#ffffff", 0, 'stroke="#000"') + c(80, 89, 26, "#7a7a7a")
               + t(80, 184, "000 / FFF", 10, INK, "Courier New, monospace", 400, "middle")),
        "mono": (P, swatches(["#0b1f3a", "#173a66", "#2f5d94", "#6f93c2", "#c3d4ea"])),
        "tonal": (P, swatches(["#5c4033", "#8b6a4f", "#b89577", "#dcc3a8", "#f2e6d8"])),
        "twotone": (P, r(10, 14, 140, 150, "#1d3557") + c(80, 89, 45, "#f1a5a5")
                    + t(80, 184, "1D3557 + F1A5A5", 9, INK, "Courier New, monospace", 400, "middle")),
        "complement": (P, r(10, 14, 140, 75, "#1f4fd1") + r(10, 89, 140, 75, "#ff8a00")
                       + t(80, 184, "1F4FD1 ↔ FF8A00", 9, INK, "Courier New, monospace", 400, "middle")),
        "primary": (P, swatches(["#d62828", "#f2b705", "#1d4e9e"])),
        "pastel": (P, swatches(["#ffc8dd", "#bde0fe", "#cdeac0", "#ffe5a3", "#e2d1f9"])),
        "muted": (P, swatches(["#8d8a80", "#a39b8b", "#7d8a86", "#b5a99a", "#6e6a63"])),
        "neon": ("#111111", "".join(r(10 + i * 28, 14, 28, 150, col) for i, col in
                                    enumerate(["#39ff14", "#ff2bd6", "#00f0ff", "#fff500", "#ff5e00"]))
                 + t(80, 184, "NEON", 12, "#ffffff", "Courier New, monospace", 700, "middle")),
        "earth": (P, swatches(["#5e3b26", "#a0522d", "#c19a6b", "#6b7f4e", "#e8d8c3"])),
        "metallic": (P, '<defs><linearGradient id="gd" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8a6d1f"/>'
                     '<stop offset=".45" stop-color="#f6e27a"/><stop offset="1" stop-color="#9c7a25"/></linearGradient>'
                     '<linearGradient id="sv" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7d828a"/>'
                     '<stop offset=".45" stop-color="#f2f4f7"/><stop offset="1" stop-color="#8b9099"/></linearGradient></defs>'
                     + r(10, 14, 70, 150, "url(#gd)") + r(80, 14, 70, 150, "url(#sv)")
                     + t(80, 184, "GOLD / SILVER", 9, INK, "Courier New, monospace", 400, "middle")),
        "wheel": (P, "".join(f'<path d="M80 92 L{80 + 62 * math.cos(math.radians(i * 30 - 90)):.1f} '
                             f'{92 + 62 * math.sin(math.radians(i * 30 - 90)):.1f} A62 62 0 0 1 '
                             f'{80 + 62 * math.cos(math.radians(i * 30 - 60)):.1f} '
                             f'{92 + 62 * math.sin(math.radians(i * 30 - 60)):.1f} Z" '
                             f'fill="hsl({i * 30},80%,55%)"/>' for i in range(12)) + c(80, 92, 24, "#ffffff")
                  + t(80, 184, "12 HUES", 10, INK, "Courier New, monospace", 400, "middle")),
        "palettes": (P, "".join(r(10 + j * 28, 18 + i * 52, 28, 44, col) for i, row in enumerate(
                     (["#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51"],
                      ["#22223b", "#4a4e69", "#9a8c98", "#c9ada7", "#f2e9e4"],
                      ["#003049", "#d62828", "#f77f00", "#fcbf49", "#eae2b7"])) for j, col in enumerate(row))
                     + t(80, 186, "PALETTES", 10, INK, "Courier New, monospace", 400, "middle")),
        "gradients": (P, '<defs><linearGradient id="g1"><stop offset="0" stop-color="#ff5f6d"/><stop offset="1" stop-color="#ffc371"/>'
                      '</linearGradient><linearGradient id="g2"><stop offset="0" stop-color="#2193b0"/><stop offset="1" '
                      'stop-color="#6dd5ed"/></linearGradient><linearGradient id="g3"><stop offset="0" stop-color="#11998e"/>'
                      '<stop offset="1" stop-color="#38ef7d"/></linearGradient></defs>'
                      + r(10, 14, 140, 46, "url(#g1)") + r(10, 66, 140, 46, "url(#g2)") + r(10, 118, 140, 46, "url(#g3)")),
        "brand": (P, r(10, 14, 140, 100, "#0a3d62") + r(10, 118, 68, 46, "#e58e26") + r(82, 118, 68, 46, "#f5f6fa", 0, 'stroke="#ccc"')
                  + t(16, 34, "PRIMARY", 9, "#ffffff", "Courier New, monospace", 700) + t(80, 184, "0A3D62 · E58E26", 9, INK,
                  "Courier New, monospace", 400, "middle")),
        "trend": (P, swatches(["#7f5539", "#d4a373", "#6b705c", "#a5a58d", "#b56576"], labels=False)
                  + "".join(figure(26 + i * 27, 40, 0.75, "#ffffff", 0.85) for i in range(5))
                  + t(80, 184, "SEASON", 10, INK, "Courier New, monospace", 400, "middle")),
        "chips": (P, "".join(r(12 + i * 48, 30, 40, 120, "#ffffff", 2, 'stroke="#cccccc"') + r(12 + i * 48, 30, 40, 80, col, 2)
                             + t(16 + i * 48, 126, col.upper().lstrip("#"), 8, INK, "Courier New, monospace", 700)
                             for i, col in enumerate(("#c0392b", "#16a085", "#f1c40f")))),
    }
    return C[name]


# ---------------------------------------------------------------- keyword -> cover

COVER = {
    # ① 레이아웃
    "격자 나누기 (그리드)": ("layout", "grid"), "칸칸이 나눈 모듈 그리드": ("layout", "modular"),
    "비대칭 배치": ("layout", "asym"), "여백 살리기": ("layout", "whitespace"),
    "중요한 것부터 크게 (위계)": ("layout", "hierarchy"), "줄 맞추기 (정렬)": ("layout", "align"),
    "잡지 표지": ("layout", "cover"), "잡지 펼침면": ("layout", "spread"), "사진으로 꽉 채운 지면": ("layout", "fullbleed"),
    "2단·3단 나누기": ("layout", "columns"), "책 내지": ("layout", "book"), "목차 디자인": ("layout", "toc"),
    "글자 중심 포스터": ("layout", "typoposter"), "사진 중심 포스터": ("layout", "photoposter"),
    "전시 포스터": ("layout", "exhibition"), "리플렛·브로슈어": ("layout", "brochure"),
    "첫 화면 랜딩 페이지": ("layout", "landing"), "도시락처럼 나눈 벤토 그리드": ("layout", "bento"),
    "카드 배치": ("layout", "cards"), "잡지 같은 웹사이트": ("layout", "editorialweb"),
    "포트폴리오 웹사이트": ("layout", "portfolio"), "모바일 앱 화면": ("layout", "mobile"),
    "발표 자료": ("layout", "slides"), "인스타그램 피드": ("layout", "feed"), "넘겨 보는 카드뉴스": ("layout", "carousel"),
    # ② 타이포그래피
    "삐침이 있는 세리프": ("font", ("Noto Serif KR, serif", "가 Aa")),
    "삐침이 없는 산세리프": ("font", ("Inter, Noto Sans KR, sans-serif", "가 Aa")),
    "패션 잡지 제목체 (디도·보도니)": ("font", ("Bodoni Moda, Didot, serif", "Vogue")),
    "고전적인 가라몽": ("font", ("EB Garamond, Garamond, serif", "Aa Gg")),
    "단단한 그로테스크": ("font", ("Space Grotesk, sans-serif", "Aa Rr")),
    "동그란 기하학 산세리프": ("font", ("Jost, Futura, sans-serif", "Aa Oo")),
    "타자기 같은 고정폭": ("font", ("IBM Plex Mono, monospace", "{ }  01")),
    "굵고 각진 슬랩 세리프": ("font", ("Roboto Slab, serif", "Aa Ss")),
    "필기체 스크립트": ("font", ("Pinyon Script, cursive", "Script")),
    "제목용 장식 서체": ("font", ("Abril Fatface, serif", "Aa Dd")),
    "명조체": ("font", ("Nanum Myeongjo, serif", "가나 명조")),
    "바탕체": ("font", ("Gowun Batang, serif", "가나 바탕")),
    "고딕체": ("font", ("Noto Sans KR, sans-serif", "가나 고딕")),
    "둥근 돋움체": ("font", ("Gowun Dodum, sans-serif", "가나 돋움")),
    "손글씨체": ("font", ("Nanum Pen Script, cursive", "손글씨")),
    "굵은 제목용 한글": ("font", ("Black Han Sans, sans-serif", "제목")),
    "레트로 한글": ("font", ("Song Myung, serif", "옛날 다방")),
    "한글 레터링": ("font", ("Yeon Sung, cursive", "레터링")),
    "헬베티카": ("font", ("Helvetica, Arial, sans-serif", "Aa Rr", "기기에 있으면 실제 서체로 보입니다")),
    "퓨추라": ("font", ("Futura, Jost, sans-serif", "Aa Oo", "기기에 있으면 실제 서체로 보입니다")),
    "보도니": ("font", ("Bodoni Moda, serif", "Aa Bb")),
    "유니버스": ("font", ("Univers, Helvetica, sans-serif", "Aa Uu", "기기에 있으면 실제 서체로 보입니다")),
    "길 산스": ("font", ("Gill Sans, Gill Sans MT, sans-serif", "Aa Gg", "기기에 있으면 실제 서체로 보입니다")),
    "인터": ("font", ("Inter, sans-serif", "Aa 01")),
    "잡지 로고 (마스트헤드)": ("fontdemo", "masthead"), "아주 큰 글자": ("fontdemo", "big"),
    "실험적인 글자 배치": ("fontdemo", "experimental"), "서체 짝짓기": ("fontdemo", "pairing"),
    "두께가 변하는 가변 폰트": ("fontdemo", "variable"), "글자 사이 간격 (자간)": ("fontdemo", "kerning"),
    "크기로 만드는 위계": ("fontdemo", "scale"), "로고용 레터링": ("fontdemo", "lettering"),
    # ③ 이미지
    "스튜디오 화보": ("photo", "studio"), "플래시 터뜨린 사진": ("photo", "flash"), "필름 카메라 느낌": ("photo", "film"),
    "흑백 사진": ("photo", "bwphoto"), "제품 정물 사진": ("photo", "stilllife"), "야외 로케이션": ("photo", "outdoor"),
    "길거리 스냅": ("photo", "street"), "얼굴 클로즈업": ("photo", "closeup"), "전신 컷": ("photo", "fullbody"),
    "움직임이 번진 사진": ("photo", "motionblur"),
    "두 가지 색 (듀오톤)": ("style", "duotone"), "망점 (하프톤)": ("treat", "halftone"), "거친 그레인 질감": ("style", "grain"),
    "오려 붙인 콜라주": ("style", "collage"), "사람만 오려 낸 컷아웃": ("treat", "cutout"), "크롬 금속 효과": ("style", "chrome"),
    "3D 그래픽": ("style", "3d"), "그라디언트": ("style", "gradient"),
    "손그림": ("style", "handdrawn"), "선으로만 그린 라인 드로잉": ("treat", "lineart"), "평면 벡터 일러스트": ("treat", "flat"),
    "리소 인쇄 느낌": ("treat", "riso"), "픽셀 아트": ("treat", "pixel"),
    "스위스 스타일": ("style", "swiss"), "바우하우스": ("style", "bauhaus"), "러시아 구성주의 포스터": ("style", "constructivism"),
    "아르데코": ("style", "deco"), "60년대 사이키델릭": ("style", "psychedelic"), "80년대 멤피스": ("style", "memphis"),
    "거칠고 투박한 브루탈리즘": ("style", "brutal"), "Y2K 그래픽": ("style", "y2k"),
    # ④ 색상
    "흑백": ("colour", "bw"), "한 가지 색 모노톤": ("colour", "mono"), "같은 계열 톤온톤": ("colour", "tonal"),
    "두 가지 색 대비": ("colour", "twotone"), "반대 색 보색 대비": ("colour", "complement"), "강렬한 원색": ("colour", "primary"),
    "파스텔": ("colour", "pastel"), "채도 낮은 색": ("colour", "muted"), "형광색": ("colour", "neon"),
    "차분한 흙빛 어스톤": ("colour", "earth"), "금속 느낌 금·은": ("colour", "metallic"),
    "색상환": ("colour", "wheel"), "컬러 팔레트 모음": ("colour", "palettes"), "그라디언트 배색": ("colour", "gradients"),
    "브랜드 컬러": ("colour", "brand"), "패션 컬러 트렌드": ("colour", "trend"), "팬톤 같은 컬러 칩": ("colour", "chips"),
}

COVER_FONTS = ["Noto Serif KR", "Noto Sans KR", "Inter", "Bodoni Moda", "EB Garamond", "Space Grotesk", "Jost",
               "IBM Plex Mono", "Roboto Slab", "Pinyon Script", "Abril Fatface", "Nanum Myeongjo", "Gowun Batang",
               "Gowun Dodum", "Nanum Pen Script", "Black Han Sans", "Song Myung", "Yeon Sung"]

_KINDS = {"style": style, "layout": layout, "fontdemo": fontdemo, "thing": thing, "photo": photo, "treat": treat,
          "colour": colour}
_IDS = ("y2k", "gr", "sp", "ch", "gn", "gl", "pt", "gd", "sv", "g1", "g2", "g3")


def cover_svg(keyword: str, uid: str) -> str:
    kind, arg = COVER[keyword]
    bg, body = font(*arg) if kind == "font" else _KINDS[kind](arg)
    for gid in _IDS:  # ids inside <defs> must be unique on the page
        body = body.replace(f'id="{gid}"', f'id="{gid}-{uid}"').replace(f"url(#{gid})", f"url(#{gid}-{uid})")
    return _svg(body, bg, keyword)
