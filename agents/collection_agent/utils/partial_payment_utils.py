from __future__ import annotations

from typing import Any


def partial_payment_from_llm_amount(
    *,
    state: dict[str, Any],
    memory_state: dict[str, Any],
    total_due: float,
) -> dict[str, float] | None:
    """Validate and calculate partial-payment details from an LLM-normalized amount.

    The LLM owns language understanding. For example, if the customer says
    "half" or "quarter", entity extraction should normalize that into a
    numeric `customer_payment_capacity`. This helper only verifies that the
    amount is a valid partial payment and performs safe arithmetic.
    """

    if total_due <= 0:
        return None

    turn_entities = (
        state.get("extracted_entities_turn")
        if isinstance(state.get("extracted_entities_turn"), dict)
        else memory_state.get("extracted_entities_turn")
    )
    turn_entities = dict(turn_entities) if isinstance(turn_entities, dict) else {}

    amount = _optional_number(turn_entities.get("customer_payment_capacity"))
    if amount is None and "customer_payment_capacity" in turn_entities:
        amount = _optional_number(state.get("customer_payment_capacity"))

    if amount is None or amount <= 0 or amount >= total_due:
        return None

    pct = round(amount / total_due * 100, 2)
    return {
        "partial_payment_amount": round(amount, 2),
        "partial_payment_pct": pct,
        "remaining_balance": round(total_due - amount, 2),
    }


def _optional_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def partial_payment_policy(memory_state: dict[str, Any]) -> dict[str, Any]:
    context = (
        memory_state.get("active_collection_context")
        if isinstance(memory_state.get("active_collection_context"), dict)
        else {}
    )
    return context.get("policy") if isinstance(context.get("policy"), dict) else {}
