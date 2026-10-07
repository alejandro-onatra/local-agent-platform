"""Deterministic routing proposes an action; policy remains independent."""
from .contracts import Message, Route


class RulesDecision:
    def decide(self, message: Message) -> Route:
        tags = {"[support]": Route.PREVIEW, "[access]": Route.REVIEW, "[security]": Route.BLOCK}
        matches = [route for tag, route in tags.items() if tag in message.subject.lower()]
        # Ambiguous or unknown input is an explicit abstention.
        return matches[0] if len(matches) == 1 else Route.ABSTAIN
