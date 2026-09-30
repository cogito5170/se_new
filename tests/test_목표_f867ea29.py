import json
import os
import sys

def test_ledgerstat():
    ledger_path = 'repair/ledger.jsonl'
    if not os.path.exists(ledger_path):
        # 2026-09-30: 수리 원장은 사람의 요청이 담긴 기록물이라 git 에 남기지 않는다(.gitignore) -- 체크아웃(CI)에는 없다.
        # 그러면 이 검사가 보던 '귀속' 줄은 여기서 **못 잰다.** 대신 그 원장이 git 밖(기계에만)이라는 것을 본다.
        import subprocess
        assert subprocess.run(["git", "check-ignore", "-q", ledger_path]).returncode == 0, \
            f"{ledger_path}가 없는데 git 이 무시하는 자리도 아니다"
        print(f"못 잼: {ledger_path} 는 기계에만 있다(git 밖) -- '귀속' 줄은 그 기계에서 본다")
        return
    
    with open(ledger_path, 'r') as f:
        lines = [json.loads(line) for line in f.readlines()]
    
    # 0이 아닐 수도 있는 열쇠들을 확인
    # "귀속" 같은 키가 없다는 것이 문제임
    for entry in lines:
        if '귀속' in entry:
            print("귀속 발견됨")
            return
            
    # 귀속 키가 없는 경우가 문제라면, 
    # 일단 테스트가 귀속 키를 가진 항목을 하나라도 찾을 수 있는지 확인해야 함
    raise AssertionError("어떤 항목에도 '귀속' 열쇠가 없습니다.")

if __name__ == "__main__":
    test_ledgerstat()
