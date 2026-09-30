# SAR 데모: 실제 정책코어(C, ctypes) + 실제 탐지기(cv2 YuNet) + 실제 이미지.
CC     ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -I../policy_core

libsarcore.so: sar_core.c ../policy_core/policy_core.c ../policy_core/policy_core.h
	$(CC) -shared -fPIC $(CFLAGS) -o libsarcore.so sar_core.c ../policy_core/policy_core.c -lm

.PHONY: assets demo clean
assets:
	bash fetch_assets.sh
demo: libsarcore.so
	python3 map_demo.py
clean:
	rm -f libsarcore.so
	rm -rf out
