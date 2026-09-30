"""한 파일짜리 인터랙티브 페이지 -> OUT/site/ruh2_lab.html
(실치수 3D 셀·BMS, 브라우저 시뮬레이터, 원자 반응 뷰어, 도면 갤러리). 라이브러리·모델·도면
썸네일을 모두 안에 넣는다 -- 디스코드로 받아 브라우저로 열면 인터넷 없이 돈다.
영상·PDF 는 같은 폴더에 두면 페이지 안에서 열린다.   python3 -m ruh2.site
"""
from __future__ import annotations

import base64
import io
import json

from ruh2 import paths

DW = ["E-001_block", "E-002_power", "E-003_sense", "E-004_mcu_safety", "M-001_vessel", "M-002_stack", "M-003_pcb"]


def _jpeg_uri(p, width):
    from PIL import Image
    im = Image.open(p).convert("RGB")
    im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    b = io.BytesIO(); im.save(b, "JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def build() -> str:
    paths.ensure()
    B = json.loads((paths.OUT / "battery.json").read_text(encoding="utf-8"))
    G = json.loads((paths.DATA / "dft_geom.json").read_text(encoding="utf-8"))
    t = (paths.WEB / "site.template.html").read_text(encoding="utf-8")
    t = t.replace("/*__DATA__*/null", json.dumps(dict(spec=B["spec"], params=B["params"], geom=G), ensure_ascii=False, separators=(",", ":")))
    V = paths.VENDOR
    lib = {"__CDN_THREE__": V / "three.min.js", "__CDN_ORBIT__": V / "OrbitControls.js",
           "__CDN_ROOM__": V / "RoomEnvironment.js", "__CDN_CHART__": V / "chart.umd.js",
           "nih2.js": paths.WEB / "nih2.js", "battery3d.js": paths.WEB / "battery3d.js", "atom3d.js": paths.WEB / "atom3d.js"}
    for k, f in lib.items():
        t = t.replace(f'<script src="{k}"></script>', "<script>\n" + f.read_text(encoding="utf-8") + "\n</script>")
    d = {}
    for n in DW:
        png = paths.DRAW / f"{n}.png"
        if png.exists():
            d[n] = _jpeg_uri(png, 2000); d[n + "_t"] = _jpeg_uri(png, 520)
    t = t.replace("const DW = [", "const DWGDATA = " + json.dumps(d) + ";\nconst DW = [")
    t = t.replace("`dwg/${f}_t.jpg`", 'DWGDATA[f + "_t"]').replace("`dwg/${f}.png`", "DWGDATA[f]")
    t = t.replace('<img src="dwg/${f}_t.jpg"', '<img src="${DWGDATA[f + "_t"] || ""}"').replace("$(\"dlgI\").src = `dwg/${f}.png`", '$("dlgI").src = DWGDATA[f]')
    html = "<!doctype html><html lang='ko'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'></head><body>" + t + "</body></html>"
    out = paths.SITE / "ruh2_lab.html"
    out.write_text(html, encoding="utf-8")
    return str(out)


if __name__ == "__main__":
    print(build())
