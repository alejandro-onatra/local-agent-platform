"""Synchronous reference orchestrator; dependencies are injected through contracts."""
from collections.abc import Callable
import time
from .contracts import (Action, ApprovalPending, ApprovalStore, AuditEvent, DecisionProvider, Message,
                        ModelResult, ModelRouter, Operation, PolicyEngine, Route,
                        Run, State, StateStore, ToolGateway, Verdict)



class Runtime:
    def __init__(self, router: ModelRouter, decisions: DecisionProvider, store: StateStore,
                 policy: PolicyEngine, approvals: ApprovalStore, tools: ToolGateway,
                 clock: Callable[[], float] = time.monotonic):
        self.router, self.decisions, self.store = router, decisions, store
        self.policy, self.approvals, self.tools, self.clock = policy, approvals, tools, clock

    def event(self, run_id: str, operation: Operation, outcome: str):
        # Only fixed operation/outcome values: no body, summary or exception text.
        self.store.record(AuditEvent(run_id, operation, outcome))

    def finish(self, run: Run, state: State, reason: str, **changes) -> Run:
        result = self.store.transition(run.run_id, run.state, state, reason=reason, **changes)
        self.event(run.run_id, Operation.RUN, state.value)
        return result

    def start(self, message: Message, actor: str) -> Run:
        if (not isinstance(message, Message) or not isinstance(actor, str) or not actor
                or not all(isinstance(value, str) for value in (message.case_id, message.subject, message.body))
                or not 1 <= len(message.case_id) <= 64 or len(message.subject) > 200 or len(message.body) > 2000):
            raise ValueError("invalid_workflow_input")
        run = self.store.create(actor)
        self.event(run.run_id, Operation.RUN, "started")
        try:
            route = self.decisions.decide(message)
            if not isinstance(route, Route):
                raise ValueError("invalid_decision")
        except Exception:
            return self.finish(run, State.FAILED, "decision_failed")
        self.event(run.run_id, Operation.DECISION, route.value)
        if route == Route.ABSTAIN:
            return self.finish(run, State.ABSTAINED, "no_matching_rule", route=route)
        tool = {Route.PREVIEW: "preview_triage", Route.REVIEW: "record_triage", Route.BLOCK: "external_send"}[route]
        action = Action(run.run_id, message.case_id, tool, "")
        try:
            verdict = self.policy.evaluate(action)
            if not isinstance(verdict, Verdict):
                raise ValueError("invalid_policy_verdict")
        except Exception:
            return self.finish(run, State.FAILED, "policy_failed", route=route)
        self.event(run.run_id, Operation.POLICY, verdict.value)
        if verdict == Verdict.DENY:
            return self.finish(run, State.DENIED, "policy_denied", route=route)
        try:
            result = self.router.select().summarize(message)
            if not isinstance(result, ModelResult) or not isinstance(result.summary, str) or not 1 <= len(result.summary) <= 256:
                raise ValueError("invalid_model_result")
        except Exception:
            self.event(run.run_id, Operation.MODEL, "failed")
            return self.finish(run, State.FAILED, "provider_failed", route=route)
        self.event(run.run_id, Operation.MODEL, "completed")
        action = Action(run.run_id, message.case_id, tool, result.summary)
        # Re-evaluate the complete action, including arguments, before requesting approval.
        try:
            verdict = self.policy.evaluate(action)
            if verdict == Verdict.APPROVAL:
                approval_id = self.approvals.request(action, actor, self.policy.version, self.clock())
                return self.finish(run, State.WAITING_APPROVAL, "approval_required", route=route,
                                   action=action, approval_id=approval_id)
            if verdict != Verdict.ALLOW:
                return self.finish(run, State.DENIED, "policy_denied", route=route)
            receipt = self.tools.execute(action, actor, None, self.clock())
        except Exception:
            self.event(run.run_id, Operation.TOOL, "failed")
            return self.finish(run, State.FAILED, "execution_failed", route=route)
        self.event(run.run_id, Operation.TOOL, "completed")
        return self.finish(run, State.COMPLETED, "preview_completed", route=route, action=action, receipt_id=receipt)

    def resume(self, run_id: str, actor: str) -> Run:
        run = self.store.get(run_id)
        if run.actor != actor:
            raise PermissionError("actor_mismatch")
        if run.state == State.COMPLETED:
            return run  # Repeated resume does not call the tool again.
        if run.state != State.WAITING_APPROVAL or run.action is None or run.approval_id is None:
            raise ValueError("run_not_waiting_for_approval")
        try:
            # Even if the new policy allows it, this pending write requires its bound approval.
            if self.policy.evaluate(run.action) != Verdict.APPROVAL:
                return self.finish(run, State.DENIED, "policy_changed")
            receipt = self.tools.execute(run.action, actor, run.approval_id, self.clock())
        except ApprovalPending:
            self.event(run_id, Operation.APPROVAL, "pending")
            return run
        except Exception:
            self.event(run_id, Operation.APPROVAL, "rejected")
            return self.finish(run, State.FAILED, "approval_or_execution_failed")
        self.event(run_id, Operation.APPROVAL, "consumed")
        self.event(run_id, Operation.TOOL, "completed")
        return self.finish(run, State.COMPLETED, "record_completed", receipt_id=receipt)
