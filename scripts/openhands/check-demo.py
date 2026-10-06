#!/usr/bin/env python3
"""Acceptance check for the synthetic task; run inside /projects/demo."""
import importlib.util
from pathlib import Path
import sys
import unittest

root = Path.cwd().resolve()
if root != Path("/projects/demo"):
    raise SystemExit("Run this acceptance check inside the demo container workspace.")
for filename in ("sum.py", "test_sum.py"):
    file = root / filename
    if not file.is_file() or file.is_symlink():
        raise SystemExit(f"Missing regular demo file: {filename}")

spec = importlib.util.spec_from_file_location("sum", root / "sum.py")
module = importlib.util.module_from_spec(spec)
sys.modules["sum"] = module
spec.loader.exec_module(module)
add = getattr(module, "add", None)
if not callable(add):
    raise SystemExit("sum.py must expose callable add(a, b).")
for a, b, expected in ((2, 3, 5), (-2, -3, -5), (-4, 4, 0), (0, 0, 0)):
    if add(a, b) != expected:
        raise SystemExit(f"Acceptance failed for add({a}, {b}).")

suite = unittest.defaultTestLoader.discover(str(root), pattern="test_sum.py")
count = suite.countTestCases()
if count < 3:
    raise SystemExit("Expected at least three unittest cases in test_sum.py.")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful() or result.testsRun < 3 or result.skipped:
    raise SystemExit("Generated tests failed, were skipped or insufficient.")
print(f"RESULT: synthetic add acceptance and {result.testsRun} generated tests passed.")
