class UnknownReference(Exception):
    """An order payload names a customer, brand or product that does not exist (HTTP 400)."""


class ManagerApprovalRequired(Exception):
    """A price above the current rate or a date past the internal due date: the agent must
    escalate instead of confirming (ADR 0010)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
