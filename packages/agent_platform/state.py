"""In-memory reference state, deliberately not a durable production adapter."""
from dataclasses import replace
from uuid import uuid4
from .contracts import AuditEvent, Run, State


class MemoryState:
    def __init__(self):
        self.runs: dict[str, Run] = {}
        self.audit: list[AuditEvent] = []

    def create(self, actor: str) -> Run:
        run = Run(str(uuid4()), State.RUNNING, actor)
        self.runs[run.run_id] = run
        return run

    def get(self, run_id: str) -> Run:
        return self.runs[run_id]

    def transition(self, run_id: str, expected: State, state: State, **changes) -> Run:
        current = self.get(run_id)
        if current.state != expected or expected not in {State.RUNNING, State.WAITING_APPROVAL}:
            raise ValueError("invalid_state_transition")
        allowed = {
            State.RUNNING: {State.WAITING_APPROVAL, State.COMPLETED, State.DENIED, State.ABSTAINED, State.FAILED},
            State.WAITING_APPROVAL: {State.COMPLETED, State.DENIED, State.FAILED},
        }
        if state not in allowed[expected] or not set(changes) <= {
            "route", "action", "approval_id", "receipt_id", "reason"
        }:
            raise ValueError("invalid_state_transition")
        updated = replace(current, state=state, **changes)
        self.runs[run_id] = updated
        return updated

    def record(self, event: AuditEvent) -> None:
        self.audit.append(event)
