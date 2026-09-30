# ssm -- 최소 선택적 SSM(Mamba 원자) 추론 커널. host_test 로 원자 거동을 붙든다.
# 코어(ssm.c)는 힙/재귀 없음 -> MCU 크로스컴파일로 그대로 이식(고정소수는 다음 단계).
CC      ?= gcc
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Werror
CORE    := ../../policy_core
CFLAGS  += -I$(CORE)
LDLIBS  ?= -lm

# host_test 는 커널(ssm.c) + 가치 head 어댑터(ssm_value.c) + 정책 코어(policy_core.c)를
# 함께 링크해 '원자 거동 + PC_ValueHead 순수성 + 코어와의 배선'까지 한 번에 붙든다.
host_test: host_test.c ssm.c ssm_value.c ssm.h ssm_value.h $(CORE)/policy_core.c $(CORE)/policy_core.h
	$(CC) $(CFLAGS) -o $@ host_test.c ssm.c ssm_value.c $(CORE)/policy_core.c $(LDLIBS)

.PHONY: test clean
test: host_test
	./host_test

clean:
	rm -f host_test

# MCU 이식 예 (커널 + 어댑터, host_test 제외):
#   arm-none-eabi-gcc -std=c99 -Os -mcpu=cortex-m4 -I../../policy_core -c ssm.c ssm_value.c
# ssm.c/ssm_value.c 는 stdio 를 안 쓴다 -> bare-metal 링크 가능. expf/logf 는 libm/LUT 로.
