"""Jev, the System One model of TypeSafe AI (ADR 0025 C): typed questions over a `state`,
structured answers with probabilities and confidence, no text generation. Optional: with
`TYPESAFE_API_KEY` empty, the `typesafe-sdk` package missing, an API error or the time budget
spent, every call returns None and the classifier goes on with Claude. The SDK surface
(`typesafe_sdk.TypeSafeClient.system_one` with `Choice`/`Noul` questions) is wrapped here and
nowhere else."""

import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)
NEW = "nuevo"
ITEM_BUDGET_SECONDS = 8.0  # Jev's total time per order item (product + materials); then Claude alone.
MIN_CALL_SECONDS = 0.5


def enabled() -> bool:
    return bool(getattr(settings, "TYPESAFE_API_KEY", ""))


class Budget:
    """Jev's time for one item, counted over Jev's own calls only (Claude's call in between does
    not spend it): each call gets what is left as its timeout."""

    def __init__(self, seconds: float = ITEM_BUDGET_SECONDS):
        self.left = seconds

    def remaining(self) -> float:
        return self.left

    def spend(self, seconds: float) -> None:
        self.left -= seconds


_cached_client: dict = {"key": None, "client": None}


def _client(timeout: float):
    """One client per process and key (its HTTP connection pool is reused, orquestador 11/10);
    the item's remaining budget goes as each call's timeout."""
    try:
        from typesafe_sdk import RetryPolicy, TypeSafeClient
    except ImportError:
        logger.warning("jev: typesafe-sdk is not installed; using Claude")
        return None
    key = (settings.TYPESAFE_API_KEY, getattr(settings, "TYPESAFE_MODEL", "") or None)
    if _cached_client["key"] != key or _cached_client["client"] is None:
        # No retries: a retry would spend the item's budget; Claude is the fallback.
        _cached_client.update(key=key, client=TypeSafeClient(api_key=key[0], model=key[1], timeout=ITEM_BUDGET_SECONDS, retry=RetryPolicy(max_retries=0)))
    return _cached_client["client"]


def reset_client() -> None:
    client = _cached_client.get("client")
    _cached_client.update(key=None, client=None)
    try:
        if client is not None and hasattr(client, "close"):
            client.close()
    except Exception:
        pass


def _ask(state: str, questions: dict, budget: Budget | None):
    """One `system_one` call with several named questions; None when Jev is off, out of time or fails."""
    if not enabled() or not questions:
        return None
    budget = budget or Budget()
    timeout = budget.remaining()
    if timeout < MIN_CALL_SECONDS:
        logger.warning("jev: time budget spent; using Claude")
        return None
    client = _client(timeout)
    if client is None:
        return None
    started = time.monotonic()
    try:
        return client.system_one(state, questions, timeout=timeout)
    except Exception as exc:  # Never block the order flow on the classifier.
        logger.warning("jev: system_one failed (%s): %s", type(exc).__name__, exc)
        return None
    finally:
        budget.spend(time.monotonic() - started)


def choose_many(state: str, questions: dict[str, tuple[dict[str, str], str]], budget: Budget | None = None) -> dict[str, tuple[str, float, dict]] | None:
    """Several `Choice` questions in ONE call: `{name: (criteria, instructions)}` with criteria as
    option -> description. Returns `{name: (choice, confidence, probabilities)}` (answers Jev left
    out are missing) or None when Jev is off or fails."""
    try:
        from typesafe_sdk import Choice
    except ImportError:
        if enabled():
            logger.warning("jev: typesafe-sdk is not installed; using Claude")
        return None
    asked = {name: Choice(criteria=criteria, instructions=instructions or None) for name, (criteria, instructions) in questions.items() if criteria}
    response = _ask(state, asked, budget)
    if response is None:
        return None
    try:
        return {name: (str(answer.choice), float(answer.confidence), dict(answer.probabilities)) for name, answer in response.choices.items() if name in asked}
    except Exception as exc:
        logger.warning("jev: unexpected answer (%s): %s", type(exc).__name__, exc)
        return None


def choose(state: str, criteria: dict[str, str], instructions: str = "", budget: Budget | None = None) -> tuple[str, float, dict] | None:
    """One `Choice` question: which key of `criteria` (option -> description) fits `state`.
    Returns (choice, confidence, probabilities) or None when Jev is off or fails."""
    if not criteria:
        return None
    answers = choose_many(state, {"choice": (criteria, instructions)}, budget)
    return (answers or {}).get("choice")


def yes(state: str, statement: str, budget: Budget | None = None) -> float | None:
    """One `Noul` question: probability that `statement` holds for `state`; None when Jev is off."""
    try:
        from typesafe_sdk import Noul
    except ImportError:
        return None
    response = _ask(state, {"guard": Noul(instructions=statement)}, budget)
    if response is None:
        return None
    answer = response.nouls.get("guard")
    return float(answer.noul) if answer is not None else None
