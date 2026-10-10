"""Outbound messages of the WhatsApp agent (ADR 0010, 0016).

`messaging.services.send_text` already routes by channel (Evolution or simulator)
and checks the allowlist. This is the second check, on the agent's side, so a bug
there can never make the bot write to a number outside the allowlist.
"""


def send(conversation, text: str, turn):
    from messaging.exceptions import NumberNotAllowed
    from messaging.services import send_text

    number = conversation.allowed_number
    if number is None or not number.active:
        raise NumberNotAllowed(f"conversation {conversation.pk}: number missing or inactive")
    if conversation.channel == "whatsapp" and number.simulated:
        raise NumberNotAllowed(f"conversation {conversation.pk}: simulated number on WhatsApp")
    return send_text(conversation, text, turn)
