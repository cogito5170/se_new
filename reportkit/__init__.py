"""기술 보고서 PDF 도구 -- 구성 정책(POLICY.md)을 코드로 강제한다.

    from reportkit import kit
    kit.build_md("보고서.md", "out.pdf")          # 정책 검사 통과해야 PDF
    python3 -m reportkit 보고서.md out.pdf         # 같은 것
    python3 -m reportkit --check 보고서.md          # 검사만

template.md 가 정책을 모두 지키는 빈 틀이다.
"""
