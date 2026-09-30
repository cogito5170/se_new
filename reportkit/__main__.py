import sys
from pathlib import Path

from reportkit import check, kit

a = [x for x in sys.argv[1:] if not x.startswith("--")]
if "--check" in sys.argv:
    body = kit.md_to_html(Path(a[0]).read_text(encoding="utf-8"), Path(a[0]).parent)
    v = check.검사(body)
    print("\n".join(v) if v else "통과")
    raise SystemExit(1 if v else 0)
r = kit.build_md(a[0], a[1] if len(a) > 1 else str(Path(a[0]).with_suffix(".pdf")), strict="--force" not in sys.argv)
print(r)
raise SystemExit(0 if r.get("ok") else 1)
