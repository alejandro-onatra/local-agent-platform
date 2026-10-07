"""Default-deny tool policy and action-bound, expiring one-use approvals."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from uuid import uuid4
from .contracts import Action, ApprovalPending, Verdict


@dataclass(frozen=True)
class LocalPolicy:
    version: str = "synthetic-v1"

    def evaluate(self, action: Action) -> Verdict:
        # A decision or model cannot grant a write permission.
        return {"preview_triage": Verdict.ALLOW,
                "record_triage": Verdict.APPROVAL}.get(action.tool, Verdict.DENY)


def fingerprint(action: Action) -> str:
    return hashlib.sha256(json.dumps(asdict(action), sort_keys=True).encode()).hexdigest()


@dataclass
class Approval:
    fingerprint: str
    actor: str
    policy_version: str
    expires_at: float
    granted: bool = False
    consumed: bool = False


class MemoryApprovals:
    def __init__(self, ttl_seconds: float = 300):
        if not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("invalid_approval_ttl")
        self.ttl = ttl_seconds
        self.requests: dict[str, Approval] = {}

    def request(self, action: Action, actor: str, policy_version: str, now: float) -> str:
        if not math.isfinite(now):
            raise ValueError("invalid_approval_time")
        approval_id = str(uuid4())
        self.requests[approval_id] = Approval(fingerprint(action), actor, policy_version, now + self.ttl)
        return approval_id

    def grant(self, approval_id: str, actor: str, now: float) -> None:
        approval = self.requests[approval_id]
        if not math.isfinite(now) or approval.actor != actor or now >= approval.expires_at or approval.consumed:
            raise ValueError("invalid_approval")
        approval.granted = True

    def consume(self, approval_id: str, action: Action, actor: str, policy_version: str, now: float) -> None:
        approval = self.requests.get(approval_id)
        if (approval is None or not math.isfinite(now) or approval.consumed
                or now >= approval.expires_at or approval.actor != actor
                or approval.policy_version != policy_version or approval.fingerprint != fingerprint(action)):
            raise ValueError("invalid_approval")
        if not approval.granted:
            raise ApprovalPending("approval_pending")
        approval.consumed = True
