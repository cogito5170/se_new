#!/usr/bin/env python3
"""Run the test suite WITHOUT pytest (stdlib only). pytest runs the same files.

    python3 tests/run_tests.py            # all tests
    python3 tests/run_tests.py -k crawl   # tests whose module or name contains 'crawl'

Supports the only fixture the tests use: `tmp_path`. Prints one line per test
and a summary; exits 1 if anything failed.
"""
from __future__ import annotations

import importlib.util
import inspect
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))


def main(argv: list[str]) -> int:
    want = argv[argv.index("-k") + 1] if "-k" in argv else None
    passed, failed, results = 0, [], []
    started = time.time()
    for path in sorted(HERE.glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:  # noqa: BLE001
            failed.append(f"{path.name} (import)")
            print(f"ERROR {path.name}: import failed\n{traceback.format_exc()}")
            continue
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if not name.startswith("test_") or fn.__module__ != mod.__name__:
                continue
            label = f"{path.stem}::{name}"
            if want and want not in label:
                continue
            tmp = Path(tempfile.mkdtemp(prefix="magref-test-"))
            kwargs = {"tmp_path": tmp} if "tmp_path" in inspect.signature(fn).parameters else {}
            t0 = time.time()
            try:
                fn(**kwargs)
                passed += 1
                print(f"PASS  {label} ({time.time() - t0:.2f}s)")
            except Exception:  # noqa: BLE001
                failed.append(label)
                print(f"FAIL  {label}\n{traceback.format_exc()}")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{passed} passed, {len(failed)} failed in {time.time() - started:.1f}s")
    for f in failed:
        print(f"  failed: {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
