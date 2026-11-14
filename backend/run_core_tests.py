"""Dependency-light runner (pytest-compatible tests; use `pytest` where installed)."""
import sys, traceback, inspect
sys.path.insert(0, ".")
import tests.test_core as t
fails = 0
for name, fn in inspect.getmembers(t, inspect.isfunction):
    if name.startswith("test_"):
        try:
            fn(); print("PASS", name)
        except Exception:
            fails += 1; print("FAIL", name); traceback.print_exc()
print("failures:", fails); sys.exit(1 if fails else 0)
