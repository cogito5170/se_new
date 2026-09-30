# fw/ — LLM 없는 자율 결정 executive (bare-metal C). 호스트 검사용 Makefile.
# 실타깃(STM32/ESP32)에서는 cross-gcc + HAL 드라이버로 링크한다(이 Makefile 은 호스트 검사 전용).

CC      ?= cc
CFLAGS  ?= -std=c99 -Wall -Wextra -Werror -O2
# 커널(도메인 무관) + 프로파일(도메인). 새 프로젝트는 profile_<도메인>.c 만 추가한다.
KERNEL   = blackboard.c estimator.c evidence.c bt.c event.c safety.c arbiter.c decision.c planner.c agent.c
PROFILES = profile_sar.c profile_min.c
SRC      = $(KERNEL) $(PROFILES)
OBJ      = $(SRC:.c=.o)

.PHONY: test clean lib
test: host_test fault_test
	./host_test
	./fault_test

host_test: host_test.c $(SRC)
	$(CC) $(CFLAGS) -o $@ host_test.c $(SRC) -lm

fault_test: fault_test.c $(SRC)
	$(CC) $(CFLAGS) -o $@ fault_test.c $(SRC) -lm

# libfw.so — sar 로 V&V 하기 위한 호스트 ctypes 글루(실타깃 펌웨어 아님)
lib: libfw.so
libfw.so: bridge.c $(SRC)
	$(CC) -std=c99 -Wall -Wextra -O2 -fPIC -shared -o $@ bridge.c $(SRC) -lm

clean:
	rm -f host_test fault_test libfw.so *.o
