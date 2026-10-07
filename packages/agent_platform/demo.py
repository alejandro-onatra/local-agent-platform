"""Run the trusted synthetic fixtures; print only structural/numeric results."""
import argparse
from collections import Counter
import json
from pathlib import Path
import yaml
from .contracts import Message, State
from .decisions import RulesDecision
from .providers import FixtureModel, StaticRouter, SubjectModel
from .runtime import Runtime
from .security import LocalPolicy, MemoryApprovals
from .state import MemoryState
from .tools import MemoryTools


def build_runtime(provider=None, clock=None):
    store, approvals, policy = MemoryState(), MemoryApprovals(), LocalPolicy()
    tools = MemoryTools(policy, approvals)
    kwargs = {} if clock is None else {"clock": clock}
    return Runtime(StaticRouter(provider or FixtureModel()), RulesDecision(), store, policy, approvals, tools, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve", action="store_true", help="Explicitly approve synthetic in-memory record actions")
    parser.add_argument("--provider", choices=("fixture", "subject"), default="fixture")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2] / "workflows/synthetic-triage/cases.yaml"
    fixture = yaml.safe_load(source.read_text())
    if fixture["version"] != 1:
        raise SystemExit("Unsupported synthetic fixture version")
    runtime = build_runtime(SubjectModel() if args.provider == "subject" else FixtureModel())
    results = []
    for item in fixture["cases"]:
        run = runtime.start(Message(item["id"], item["subject"], item["body"]), "synthetic-operator")
        if args.approve and run.state == State.WAITING_APPROVAL:
            runtime.approvals.grant(run.approval_id, run.actor, runtime.clock())
            run = runtime.resume(run.run_id, run.actor)
        expected = item["expected_approved" if args.approve else "expected"]
        results.append({"case": item["id"], "state": run.state.value,
                        "reason": run.reason, "matches_expected": run.state.value == expected})
    passed = all(item["matches_expected"] for item in results)
    print(json.dumps({"status": "passed" if passed else "failed", "provider": args.provider,
                      "cases": results, "recorded_actions": len(runtime.tools.receipts),
                      "audit_counts": dict(Counter(event.operation.value for event in runtime.store.audit)),
                      "scope": "Offline synthetic workflow; state/approvals/audit in memory; no OTLP export"}, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
