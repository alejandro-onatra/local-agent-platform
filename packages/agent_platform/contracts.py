"""Small contracts shared by runtime, providers, state and authorization."""
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ApprovalPending(ValueError):
    """An otherwise valid request still needs an explicit operator grant."""


class State(StrEnum):
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    DENIED = "denied"
    ABSTAINED = "abstained"
    FAILED = "failed"


class Route(StrEnum):
    PREVIEW = "preview"
    REVIEW = "review"
    BLOCK = "block"
    ABSTAIN = "abstain"


class Verdict(StrEnum):
    ALLOW = "allow"
    APPROVAL = "approval"
    DENY = "deny"


class Operation(StrEnum):
    RUN = "agent.run"
    DECISION = "decision.route"
    MODEL = "llm.request"
    POLICY = "policy.evaluate"
    TOOL = "tool.call"
    APPROVAL = "approval.evaluate"


@dataclass(frozen=True)
class Message:
    case_id: str
    subject: str
    body: str


@dataclass(frozen=True)
class ModelResult:
    summary: str


@dataclass(frozen=True)
class Action:
    run_id: str
    case_id: str
    tool: str
    summary: str


@dataclass(frozen=True)
class Run:
    run_id: str
    state: State
    actor: str
    route: Route | None = None
    action: Action | None = None
    approval_id: str | None = None
    receipt_id: str | None = None
    reason: str = "started"


@dataclass(frozen=True)
class AuditEvent:
    run_id: str
    operation: Operation
    outcome: str


class ModelProvider(Protocol):
    def summarize(self, message: Message) -> ModelResult: ...


class ModelRouter(Protocol):
    def select(self) -> ModelProvider: ...


class DecisionProvider(Protocol):
    def decide(self, message: Message) -> Route: ...


class StateStore(Protocol):
    def create(self, actor: str) -> Run: ...
    def get(self, run_id: str) -> Run: ...
    def transition(self, run_id: str, expected: State, state: State, **changes) -> Run: ...
    def record(self, event: AuditEvent) -> None: ...


class PolicyEngine(Protocol):
    version: str
    def evaluate(self, action: Action) -> Verdict: ...


class ApprovalStore(Protocol):
    def request(self, action: Action, actor: str, policy_version: str, now: float) -> str: ...
    def grant(self, approval_id: str, actor: str, now: float) -> None: ...
    def consume(self, approval_id: str, action: Action, actor: str, policy_version: str, now: float) -> None: ...


class ToolGateway(Protocol):
    def execute(self, action: Action, actor: str, approval_id: str | None, now: float) -> str | None: ...
