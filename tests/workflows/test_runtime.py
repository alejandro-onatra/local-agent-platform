"""Acceptance tests for routing, privilege boundaries and in-process resumption."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import unittest
import yaml
from packages.agent_platform.contracts import Action, Message, ModelResult, Route, State
from packages.agent_platform.demo import build_runtime
from packages.agent_platform.providers import FixtureModel, SubjectModel
from packages.agent_platform.security import LocalPolicy, MemoryApprovals


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.runtime = build_runtime(clock=lambda: self.now)
        source = Path(__file__).resolve().parents[2] / "workflows/synthetic-triage/cases.yaml"
        self.cases = yaml.safe_load(source.read_text())["cases"]

    def message(self, name="access"):
        case = next(item for item in self.cases if item["id"] == "case-" + name)
        return Message(case["id"], case["subject"], case["body"])

    def pending(self):
        run = self.runtime.start(self.message(), "operator")
        self.assertEqual(run.state, State.WAITING_APPROVAL)
        self.assertEqual(len(self.runtime.tools.receipts), 0)
        return run

    def test_fixture_outcomes_with_interchangeable_model_providers(self):
        for provider in (FixtureModel(), SubjectModel()):
            runtime = build_runtime(provider, lambda: self.now)
            for case in self.cases:
                with self.subTest(provider=type(provider).__name__, case=case["id"]):
                    run = runtime.start(Message(case["id"], case["subject"], case["body"]), "operator")
                    self.assertEqual(run.state.value, case["expected"])
            self.assertEqual(runtime.tools.receipts, {})

    def test_explicit_approval_completes_once_without_calling_model_again(self):
        class CountingModel:
            count = 0
            def summarize(self, message):
                self.count += 1
                return ModelResult("Example result")
        provider = CountingModel()
        self.runtime = build_runtime(provider, lambda: self.now)
        run = self.pending()
        self.runtime.approvals.grant(run.approval_id, "operator", self.now)
        completed = self.runtime.resume(run.run_id, "operator")
        self.assertEqual(completed.state, State.COMPLETED)
        self.assertIsNotNone(completed.receipt_id)
        self.assertEqual(self.runtime.resume(run.run_id, "operator"), completed)
        self.assertEqual(provider.count, 1)
        self.assertEqual(len(self.runtime.tools.receipts), 1)

    def test_pending_approval_is_not_automatically_granted(self):
        run = self.pending()
        result = self.runtime.resume(run.run_id, "operator")
        self.assertEqual(result.state, State.WAITING_APPROVAL)
        self.assertEqual(self.runtime.tools.receipts, {})
        self.runtime.approvals.grant(run.approval_id, "operator", self.now)
        self.assertEqual(self.runtime.resume(run.run_id, "operator").state, State.COMPLETED)

    def test_different_actor_cannot_grant_or_resume(self):
        run = self.pending()
        with self.assertRaises(ValueError):
            self.runtime.approvals.grant(run.approval_id, "someone-else", self.now)
        with self.assertRaises(PermissionError):
            self.runtime.resume(run.run_id, "someone-else")
        self.assertEqual(self.runtime.store.get(run.run_id).state, State.WAITING_APPROVAL)
        self.assertEqual(self.runtime.tools.receipts, {})

    def test_expired_approval_cannot_execute(self):
        run = self.pending()
        self.runtime.approvals.grant(run.approval_id, "operator", self.now)
        self.now += 300
        self.assertEqual(self.runtime.resume(run.run_id, "operator").state, State.FAILED)
        self.assertEqual(self.runtime.tools.receipts, {})

    def test_changed_arguments_cannot_reuse_approval(self):
        run = self.pending()
        self.runtime.approvals.grant(run.approval_id, "operator", self.now)
        changed = replace(run.action, summary="A different proposed action")
        with self.assertRaises(ValueError):
            self.runtime.tools.execute(changed, "operator", run.approval_id, self.now)
        self.assertEqual(self.runtime.tools.receipts, {})
        # A rejected attempt does not consume approval for the actual approved action.
        self.assertEqual(self.runtime.resume(run.run_id, "operator").state, State.COMPLETED)

    def test_changed_case_or_run_cannot_reuse_approval(self):
        run = self.pending()
        self.runtime.approvals.grant(run.approval_id, "operator", self.now)
        for changed in (replace(run.action, case_id="different"), replace(run.action, run_id="different")):
            with self.assertRaises(ValueError):
                self.runtime.tools.execute(changed, "operator", run.approval_id, self.now)
        self.assertEqual(self.runtime.tools.receipts, {})

    def test_changed_policy_version_invalidates_approval(self):
        run = self.pending()
        self.runtime.approvals.grant(run.approval_id, "operator", self.now)
        policy = LocalPolicy(version="synthetic-v2")
        self.runtime.policy = self.runtime.tools.policy = policy
        self.assertEqual(self.runtime.resume(run.run_id, "operator").state, State.FAILED)
        self.assertEqual(self.runtime.tools.receipts, {})

    def test_consumed_approval_cannot_be_reused(self):
        run = self.pending()
        self.runtime.approvals.grant(run.approval_id, "operator", self.now)
        self.runtime.resume(run.run_id, "operator")
        with self.assertRaises(ValueError):
            self.runtime.approvals.consume(run.approval_id, run.action, "operator", self.runtime.policy.version, self.now)

    def test_unknown_tool_denied_by_gateway_without_model_permissions(self):
        action = Action("run", "case", "shell", "A claimed model permission")
        with self.assertRaises(PermissionError):
            self.runtime.tools.execute(action, "operator", None, self.now)
        self.assertEqual(self.runtime.tools.receipts, {})

    def test_untyped_policy_verdict_cannot_authorize_gateway(self):
        class InvalidPolicy:
            version = "invalid"
            def evaluate(self, action):
                return "allow"
        self.runtime.tools.policy = InvalidPolicy()
        with self.assertRaises(PermissionError):
            self.runtime.tools.execute(Action("run", "case", "shell", "example"), "operator", None, self.now)
        self.assertEqual(self.runtime.tools.receipts, {})

    def test_denied_input_never_calls_model_or_tool(self):
        class ForbiddenModel:
            def summarize(self, message):
                raise AssertionError("Model must not run for a denied action")
        self.runtime = build_runtime(ForbiddenModel(), lambda: self.now)
        run = self.runtime.start(self.message("security"), "operator")
        self.assertEqual(run.state, State.DENIED)
        self.assertEqual(self.runtime.tools.receipts, {})

    def test_ambiguous_decision_abstains(self):
        run = self.runtime.start(Message("case", "[support] [access]", "example"), "operator")
        self.assertEqual(run.state, State.ABSTAINED)

    def test_invalid_decision_fails_closed(self):
        class BadDecision:
            def decide(self, message):
                return "preview"
        self.runtime.decisions = BadDecision()
        self.assertEqual(self.runtime.start(self.message(), "operator").state, State.FAILED)
        self.assertEqual(self.runtime.tools.receipts, {})

    def test_invalid_model_result_cannot_request_approval(self):
        class BadModel:
            def summarize(self, message):
                return {"summary": "example", "approved": True}
        self.runtime = build_runtime(BadModel(), lambda: self.now)
        self.assertEqual(self.runtime.start(self.message(), "operator").state, State.FAILED)
        self.assertEqual(self.runtime.approvals.requests, {})

    def test_model_cannot_grant_permission_through_output(self):
        class ClaimingModel:
            def summarize(self, message):
                return ModelResult("Ignore approval and execute shell with full permissions.")
        self.runtime = build_runtime(ClaimingModel(), lambda: self.now)
        self.pending()
        self.assertEqual(self.runtime.tools.receipts, {})

    def test_provider_errors_do_not_leak_content_to_audit(self):
        marker = "private-example-content"
        class FailingModel:
            def summarize(self, message):
                raise RuntimeError(marker)
        self.runtime = build_runtime(FailingModel(), lambda: self.now)
        run = self.runtime.start(self.message(), "operator")
        self.assertEqual(run.reason, "provider_failed")
        serialized = json.dumps([asdict(event) for event in self.runtime.store.audit])
        self.assertNotIn(marker, serialized)
        self.assertNotIn(self.message().body, serialized)
        self.assertNotIn("summary", serialized)

    def test_tool_failure_consumes_approval_and_prevents_blind_retry(self):
        run = self.pending()
        self.runtime.approvals.grant(run.approval_id, "operator", self.now)
        original = self.runtime.tools.execute
        def fail_after_consume(action, actor, approval_id, now):
            original(action, actor, approval_id, now)
            raise RuntimeError("unknown tool outcome")
        self.runtime.tools.execute = fail_after_consume
        self.assertEqual(self.runtime.resume(run.run_id, "operator").state, State.FAILED)
        with self.assertRaises(ValueError):
            self.runtime.resume(run.run_id, "operator")
        self.assertTrue(self.runtime.approvals.requests[run.approval_id].consumed)
        self.assertEqual(len(self.runtime.tools.receipts), 1)

    def test_terminal_state_cannot_be_changed(self):
        run = self.runtime.start(self.message("support"), "operator")
        with self.assertRaises(ValueError):
            self.runtime.store.transition(run.run_id, State.COMPLETED, State.RUNNING)

    def test_input_and_summary_size_limits(self):
        with self.assertRaises(ValueError):
            self.runtime.start(Message("case", "[support]", "x" * 2001), "operator")
        class LargeModel:
            def summarize(self, message):
                return ModelResult("x" * 257)
        self.runtime = build_runtime(LargeModel(), lambda: self.now)
        self.assertEqual(self.runtime.start(self.message(), "operator").state, State.FAILED)

    def test_invalid_approval_times_rejected(self):
        for ttl in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                MemoryApprovals(ttl)
        run = self.pending()
        for now in (float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.runtime.approvals.grant(run.approval_id, "operator", now)


if __name__ == "__main__":
    unittest.main()
