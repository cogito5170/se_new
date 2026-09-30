import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_goal_fe2bc1e0():
    assert os.path.exists("tests/test_목표_fe2bc1e0.py"), "검사 파일 존재해야 함"
    import plan
    assert os.path.exists("plan/할일.py"), "plan/할일.py 존재해야 함"
    assert os.path.exists("plan/할일.jsonl"), "plan/할일.jsonl 존재해야 함"
    # 2026-09-30: 개선 · 수리 원장은 기록물이라 git 에 남기지 않는다 -- 체크아웃에는 없을 수 있다. 있거나, git 밖 자리여야 한다.
    import subprocess
    def 자리(p):
        return os.path.exists(p) or subprocess.run(["git", "check-ignore", "-q", p]).returncode == 0
    assert 자리("improve/ledger.jsonl") and 자리("repair/ledger.jsonl"), "개선/수리 원장 자리(있거나 git 밖)"

if __name__ == '__main__':
    test_goal_fe2bc1e0()
    print("SUCCESS: test_목표_fe2bc1e0 passed")
