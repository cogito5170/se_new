"""IV&V: SUT / Reference / Evaluator 를 서로 모르게 분리한다(자기채점 제거).

reference.py  독립 참조세계 — **다른 물리 formulation** + 숨은 truth. observe() 는 관측만 준다.
sut.py        피시험 시스템(정책) — 관측만 먹고 결정을 낸다. reference·evaluator 를 import 안 한다.
evaluator.py  독립 평가기 — truth 를 쥐고 SUT 출력을 채점. 정책을 안 돌린다.
harness.py    셋을 정해진 인터페이스로만 잇고 숨은 시나리오 집합을 돌린다.

핵심(NASA IV&V·STD-7009B): SUT 가 truth 를 못 보고, 참조세계가 SUT 와 **다른 가정**을 써야
공통 가정에 동조한 systematic error 를 잡는다. 결과는 independent simulation-based evidence 이며
유효 validation domain 을 명시한다(현장 validation 아님).
"""
