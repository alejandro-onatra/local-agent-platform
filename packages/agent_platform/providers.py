"""Offline providers used to verify the contract without inference or credentials."""
from dataclasses import dataclass
from .contracts import Message, ModelProvider, ModelResult


class FixtureModel:
    def summarize(self, message: Message) -> ModelResult:
        return ModelResult("Synthetic message received for triage.")


class SubjectModel:
    def summarize(self, message: Message) -> ModelResult:
        # A second test double with different output, not a real language model.
        return ModelResult("Synthetic support request." if "[support]" in message.subject.lower()
                           else "Synthetic access review request.")


@dataclass(frozen=True)
class StaticRouter:
    provider: ModelProvider

    def select(self) -> ModelProvider:
        return self.provider
