#!/usr/bin/env python3
"""Run only inside the exercise container; baseline fails as expected, acceptance passes."""
import argparse
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import unittest

parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=("baseline", "acceptance"))
args = parser.parse_args()
root = Path.cwd().resolve()
if root != Path("/projects/bugfix"):
    raise SystemExit("Run inside /projects/bugfix in the agent container.")

suite = unittest.defaultTestLoader.discover(str(root), pattern="test_discounts.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if args.mode == "baseline":
    expected = {"test_ten_percent", "test_quarter_discount", "test_full_discount"}
    failed = {test.id().rsplit(".", 1)[-1] for test, _ in result.failures}
    if result.testsRun != 5 or failed != expected or result.errors or result.skipped:
        raise SystemExit("Unexpected baseline: expected exactly the three discount failures.")
    print("RESULT: expected baseline verified: 3 failures, 2 passes. Ready for agent repair.")
else:
    if not result.wasSuccessful() or result.testsRun != 5 or result.skipped:
        raise SystemExit("Original tests must all pass without skips.")
    from discounts import discounted_total
    for amount, rate, expected in (("99.99", "15", "84.99"),
                                    ("10", "12.5", "8.75"),
                                    ("0", "50", "0.00"),
                                    ("0.05", "50", "0.03")):
        value = discounted_total(Decimal(amount), Decimal(rate))
        if not isinstance(value, Decimal) or value != Decimal(expected):
            raise SystemExit(f"Independent acceptance failed for amount={amount}, rate={rate}.")
    print("RESULT: 5 unchanged tests and 4 additional Decimal/rounding checks passed.")
