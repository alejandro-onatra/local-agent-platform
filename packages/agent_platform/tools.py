"""Synthetic tool gateway. No filesystem, network, shell or external-account effects."""
from uuid import uuid4
from .contracts import Action, ApprovalStore, PolicyEngine, Verdict


class MemoryTools:
    def __init__(self, policy: PolicyEngine, approvals: ApprovalStore):
        self.policy = policy
        self.approvals = approvals
        self.receipts: dict[str, str] = {}

    def execute(self, action: Action, actor: str, approval_id: str | None, now: float) -> str | None:
        verdict = self.policy.evaluate(action)
        if not isinstance(verdict, Verdict) or verdict == Verdict.DENY:
            raise PermissionError("policy_denied")
        if verdict == Verdict.ALLOW:
            return None  # Preview is read-only.
        if verdict != Verdict.APPROVAL or approval_id is None:
            raise PermissionError("approval_required")
        if action.run_id in self.receipts:
            raise ValueError("duplicate_tool_execution")
        self.approvals.consume(approval_id, action, actor, self.policy.version, now)
        receipt = str(uuid4())
        self.receipts[action.run_id] = receipt
        return receipt
