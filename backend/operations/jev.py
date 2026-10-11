"""Jev, the System One model of TypeSafe AI (ADR 0025 C): typed questions over a `state`,
structured answers with probabilities and confidence, no text generation. Optional: with
`TYPESAFE_API_KEY` empty (or the `typesafe-sdk` package missing) every call returns None and
the classifier falls back to Claude. The exact SDK surface is wrapped here and nowhere else."""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)
NEW = "nuevo"


def enabled() -> bool:
    return bool(getattr(settings, "TYPESAFE_API_KEY", ""))


def _client():
    try:
        from typesafe import TypeSafeClient  # typesafe-sdk
    except ImportError:
        logger.info("jev: typesafe-sdk is not installed; using Claude")
        return None
    return TypeSafeClient(api_key=settings.TYPESAFE_API_KEY)


def choose(state: str, criteria: dict[str, str], instructions: str = "") -> tuple[str, float, dict] | None:
    """One `Choice` question: which key of `criteria` (option -> description) fits `state`.
    Returns (choice, confidence, probabilities) or None when Jev is off or fails."""
    if not enabled() or not criteria:
        return None
    client = _client()
    if client is None:
        return None
    try:
        from typesafe import Choice

        question = Choice(name="choice", options=list(criteria), descriptions=criteria, instructions=instructions)
        answer = client.ask(state=state, questions=[question], model=getattr(settings, "TYPESAFE_MODEL", "jev-latest"))
        result = answer["choice"] if isinstance(answer, dict) else getattr(answer, "choice", answer)
        value = getattr(result, "value", None) or (result.get("value") if isinstance(result, dict) else None)
        confidence = float(getattr(result, "confidence", None) or (result.get("confidence") if isinstance(result, dict) else 0) or 0)
        probabilities = getattr(result, "probabilities", None) or (result.get("probabilities") if isinstance(result, dict) else {}) or {}
        if value is None:
            return None
        return str(value), confidence, dict(probabilities)
    except Exception as exc:  # Never block the order flow on the classifier.
        logger.warning("jev: choose failed: %s", exc)
        return None


def yes(state: str, statement: str) -> float | None:
    """One `Noul` guard: probability that `statement` holds for `state`; None when Jev is off."""
    if not enabled():
        return None
    client = _client()
    if client is None:
        return None
    try:
        from typesafe import Noul

        answer = client.ask(state=state, questions=[Noul(name="guard", statement=statement)], model=getattr(settings, "TYPESAFE_MODEL", "jev-latest"))
        result = answer["guard"] if isinstance(answer, dict) else getattr(answer, "guard", answer)
        probability = getattr(result, "probability", None) or (result.get("probability") if isinstance(result, dict) else None)
        return float(probability) if probability is not None else None
    except Exception as exc:
        logger.warning("jev: yes failed: %s", exc)
        return None
