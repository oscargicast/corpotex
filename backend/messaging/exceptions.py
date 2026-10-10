class NumberNotAllowed(Exception):
    """The conversation's number is inactive or simulated on a WhatsApp send."""


class SendFailed(Exception):
    """Evolution did not accept the message."""


class ForeignPurchaseOrder(Exception):
    """The purchase order does not belong to the conversation's supplier."""
