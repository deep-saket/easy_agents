"""Pure helpers shared by split plan-proposal nodes."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from src.nodes.types import AgentState


def fresh_debug_state() -> dict[str, Any]:
    return {
        "prompt": None,
        "system_prompt": None,
        "llm_response": None,
        "llm_error": None,
    }


def latest_observation(state: AgentState) -> dict[str, Any] | None:
    observations = state.get("observations")
    if isinstance(observations, list):
        for item in reversed(observations):
            if isinstance(item, dict):
                return item
    observation = state.get("observation")
    return dict(observation) if isinstance(observation, dict) else None


def is_plan_rejection(text: str) -> bool:
    lowered = text.lower()
    return any(key in lowered for key in ["not work", "can't", "cannot", "too high", "reject", "no,", "no "])


def is_plan_request(text: str) -> bool:
    lowered = text.lower()
    return any(key in lowered for key in ["payment plan", "plan option", "need plan", "proposal"])


def extract_amount(text: str) -> float | None:
    match = re.search(r"(?:\$|inr\s*)?(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1))


def needs_discount_specialist(text: str) -> bool:
    lowered = text.lower()
    keywords = [
        "discount",
        "waiver",
        "concession",
        "settlement",
        "settle for",
        "counter offer",
        "counter-offer",
        "exception",
        "manager approval",
    ]
    return any(keyword in lowered for keyword in keywords)


def verification_required_fields(memory_state: dict[str, Any]) -> list[str]:
    required = memory_state.get("active_verification_required_fields")
    required_fields = [str(x).strip().lower() for x in required if str(x).strip()] if isinstance(required, list) else []
    if required_fields:
        return sorted(set(required_fields))
    return ["dob", "phone"]


def overlay_verification_state_from_graph(*, state: AgentState, memory_state: dict[str, Any]) -> dict[str, Any]:
    merged = dict(memory_state)
    if isinstance(state.get("verification_entities"), dict):
        merged["verification_entities"] = dict(state.get("verification_entities", {}))
        merged["verification_collected"] = dict(state.get("verification_entities", {}))
    if isinstance(state.get("verification_missing_fields"), list):
        merged["verification_missing_fields"] = [
            str(x).strip().lower() for x in state.get("verification_missing_fields", []) if str(x).strip()
        ]
    if isinstance(state.get("verification_verified_fields"), list):
        merged["verification_verified_fields"] = [
            str(x).strip().lower() for x in state.get("verification_verified_fields", []) if str(x).strip()
        ]
    for key in ("verified_dob", "verified_mobile", "identity_verified"):
        if key in state:
            merged[key] = bool(state.get(key))
    return merged


def overlay_negotiation_state_from_graph(*, state: AgentState, memory_state: dict[str, Any]) -> dict[str, Any]:
    merged = dict(memory_state)
    for key in (
        "conversation_mode",
        "negotiation_stage",
        "customer_payment_posture",
        "response_mode",
        "active_dialogue_owner",
        "hold_response",
        "discount_response",
    ):
        if key in state and str(state.get(key, "")).strip():
            merged[key] = str(state.get(key, "")).strip()

    memory_discount_stage = str(memory_state.get("discount_stage", "")).strip().lower()
    graph_discount_stage = str(state.get("discount_stage", "")).strip().lower()
    tool_derived_discount_stages = {
        "evaluating",
        "offered",
        "applied",
        "sms_sent",
        "confirmed",
    }
    if memory_discount_stage in tool_derived_discount_stages:
        merged["discount_stage"] = memory_discount_stage
    elif graph_discount_stage:
        merged["discount_stage"] = graph_discount_stage

    for key in (
        "customer_payment_capacity",
        "customer_payment_capacity_pct",
        "customer_payment_willingness",
    ):
        if key in state and state.get(key) is not None:
            merged[key] = state.get(key)
    for key in (
        "discount_requested",
        "discount_offered",
        "discount_accepted",
        "discount_rejected",
        "counter_offer_present",
    ):
        if key in state or key in memory_state:
            merged[key] = bool(memory_state.get(key, False)) or bool(state.get(key, False))
    effective_discount_stage = str(merged.get("discount_stage", "")).strip().lower()
    if effective_discount_stage in {"offered", "applied", "sms_sent", "confirmed"}:
        merged["discount_offered"] = True
    if effective_discount_stage in {"applied", "sms_sent", "confirmed"}:
        merged["discount_accepted"] = True
    if isinstance(state.get("customer_payment_posture_history"), list):
        merged["customer_payment_posture_history"] = list(state.get("customer_payment_posture_history", []))
    if isinstance(state.get("hardship_context"), dict):
        merged["hardship_context"] = dict(state.get("hardship_context", {}))
    for key in (
        "customer_profile",
        "customer_profile_summary",
        "payment_history",
        "payment_history_summary",
        "offer_history",
        "offer_history_summary",
        "active_collection_context",
    ):
        if isinstance(state.get(key), dict):
            merged[key] = dict(state.get(key, {}))
    if isinstance(state.get("assistance_programs"), list):
        merged["assistance_programs"] = [dict(item) for item in state.get("assistance_programs", []) if isinstance(item, dict)]
    return merged


def effective_mode(*, memory_state: dict[str, Any], default: str) -> str:
    conversation_mode = str(memory_state.get("conversation_mode", "")).strip().lower()
    hardship_context = memory_state.get("hardship_context") if isinstance(memory_state.get("hardship_context"), dict) else {}
    if conversation_mode == "hardship_negotiation" or bool(hardship_context.get("hardship_detected", False)):
        return "hardship_negotiation"
    return str(default or "strict_collections")


def render_prompt_template(template: str, values: dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered


def get_existing_conversation_plan(*, state: AgentState, memory_state: dict[str, Any]) -> dict[str, Any]:
    state_plan = state.get("conversation_plan")
    if isinstance(state_plan, dict) and state_plan:
        return dict(state_plan)
    memory_plan = memory_state.get("active_conversation_plan")
    if isinstance(memory_plan, dict) and memory_plan:
        return dict(memory_plan)
    return {}


def node_label(plan: dict[str, Any], node_id: str) -> str:
    for node in plan.get("nodes", []):
        if isinstance(node, dict) and str(node.get("id", "")) == node_id:
            return str(node.get("label", node_id)).strip() or node_id
    return node_id


def is_conversation_termination(text: str) -> bool:
    lowered = text.lower().strip()
    return lowered in {"bye", "goodbye", "end call", "stop calling"} or any(
        phrase in lowered for phrase in ["call me later", "not interested anymore"]
    )


def is_right_party_denial(text: str, *, awaiting_confirmation: bool) -> bool:
    lowered = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not lowered:
        return False
    if awaiting_confirmation and lowered in {"no", "nope", "nah"}:
        return True
    denial_phrases = [
        "not me",
        "i am not",
        "i'm not",
        "wrong person",
        "wrong number",
        "they are not here",
        "they're not here",
        "he is not here",
        "he's not here",
        "she is not here",
        "she's not here",
        "not available",
        "can i take a message",
        "i can take a message",
    ]
    return any(phrase in lowered for phrase in denial_phrases)


def looks_like_callback_time(text: str) -> bool:
    lowered = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not lowered or lowered in {"no", "nope", "not sure", "don't know", "do not know"}:
        return False
    temporal_terms = [
        "today",
        "tomorrow",
        "morning",
        "afternoon",
        "evening",
        "tonight",
        "later",
        "weekend",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "next week",
        "after ",
        "before ",
        "around ",
    ]
    return any(term in lowered for term in temporal_terms) or bool(
        re.search(r"\b(?:at\s*)?\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?\b", lowered)
    )


def normalize_callback_time(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "").strip())
    value = re.sub(
        r"(?i)^(?:please\s+)?(?:try|call|reach)(?:\s+(?:again|back|him|her|them))*\s+",
        "",
        value,
    ).strip(" .")
    return value or str(text or "").strip()


def mark_confirmation_delivered(memory: Any) -> dict[str, Any]:
    """Complete confirmation and move the active plan to closing."""

    memory_state = dict(getattr(memory, "state", {}))
    plan = (
        dict(memory_state.get("active_conversation_plan", {}))
        if isinstance(memory_state.get("active_conversation_plan"), dict)
        else {}
    )
    if not plan:
        return {}

    now = datetime.now(UTC).isoformat()
    markers = dict(plan.get("step_markers", {})) if isinstance(plan.get("step_markers"), dict) else {}
    completed_prerequisites: list[str] = []
    if str(memory_state.get("partial_payment_stage", "")).strip().lower() == "confirmed":
        details = (
            memory_state.get("partial_payment_details")
            if isinstance(memory_state.get("partial_payment_details"), dict)
            else {}
        )
        sms = details.get("sms_confirmation") if isinstance(details.get("sms_confirmation"), dict) else {}
        if (
            str(details.get("payment_reference_id", "")).strip()
            and str(sms.get("status", "")).strip().lower() == "sent"
        ):
            completed_prerequisites = ["partial_amount", "partial_link"]
            for node_id in completed_prerequisites:
                markers[node_id] = {
                    "state": "done",
                    "updated_at": now,
                    "source": "response_render",
                    "reason": "payment_link_created_and_sms_sent",
                }
    markers["confirmation"] = {
        "state": "done",
        "updated_at": now,
        "source": "response_render",
        "reason": "agreed_outcome_and_reference_delivered",
    }
    markers["close_conversation"] = {
        "state": "pending",
        "updated_at": now,
        "source": "response_render",
        "reason": "awaiting_customer_closing_reply",
    }

    nodes = [dict(node) for node in plan.get("nodes", []) if isinstance(node, dict)]
    for node in nodes:
        node_id = str(node.get("id", "")).strip()
        if node_id in completed_prerequisites or node_id == "confirmation":
            node["status"] = "done"
        elif node_id == "close_conversation":
            node["status"] = "in_progress"

    plan["nodes"] = nodes
    plan["step_markers"] = markers
    plan["previous_node_id"] = "confirmation"
    plan["current_node_id"] = "close_conversation"
    plan["next_node_ids"] = []
    plan["status"] = "active"
    plan["updated_from"] = "response_render"
    transition_update = {
        "origin": "response_render",
        "operation": "advance",
        "mark_done": [*completed_prerequisites, "confirmation"],
        "current_node_id": "close_conversation",
    }

    timeline = list(plan.get("timeline", [])) if isinstance(plan.get("timeline"), list) else []
    timeline.append(
        {
            "at_utc": now,
            "version": int(plan.get("version", 1) or 1),
            "status": "active",
            "current_node_id": "close_conversation",
            "next_node_ids": [],
            "update": transition_update,
        }
    )
    plan["timeline"] = timeline[-40:]

    snapshot_plan = {
        "plan_id": str(plan.get("plan_id", "")),
        "version": int(plan.get("version", 1) or 1),
        "status": "active",
        "mode": str(plan.get("mode", "strict_collections")),
        "objective": str(plan.get("objective", "")),
        "root_node_id": str(plan.get("root_node_id", "")),
        "current_node_id": "close_conversation",
        "previous_node_id": "confirmation",
        "next_node_ids": [],
        "nodes": [dict(node) for node in nodes],
        "edges": [dict(edge) for edge in plan.get("edges", []) if isinstance(edge, dict)],
        "step_markers": dict(markers),
        "updated_from": "response_render",
        "last_response_target": str(plan.get("last_response_target", "")),
    }
    snapshots = (
        list(plan.get("timeline_snapshots", []))
        if isinstance(plan.get("timeline_snapshots"), list)
        else []
    )
    snapshots.append(
        {
            "at_utc": now,
            "version": int(plan.get("version", 1) or 1),
            "status": "active",
            "current_node_id": "close_conversation",
            "update": dict(transition_update),
            "plan": snapshot_plan,
        }
    )
    plan["timeline_snapshots"] = snapshots[-80:]
    memory.set_state(active_conversation_plan=plan)
    return plan


def finalize_conversation_memory(memory: Any) -> None:
    """Marks the active plan and session closed after transport grace expires."""

    memory_state = dict(getattr(memory, "state", {}))
    plan = (
        dict(memory_state.get("active_conversation_plan", {}))
        if isinstance(memory_state.get("active_conversation_plan"), dict)
        else {}
    )
    if plan:
        now = datetime.now(UTC).isoformat()
        markers = dict(plan.get("step_markers", {})) if isinstance(plan.get("step_markers"), dict) else {}
        markers["close_conversation"] = {
            "state": "done",
            "updated_at": now,
            "source": "conversation_manager_timer",
            "reason": "termination_grace_period_elapsed",
        }
        nodes = [dict(node) for node in plan.get("nodes", []) if isinstance(node, dict)]
        for node in nodes:
            if str(node.get("id", "")).strip() == "close_conversation":
                node["status"] = "done"
        plan["nodes"] = nodes
        plan["step_markers"] = markers
        plan["current_node_id"] = "close_conversation"
        plan["next_node_ids"] = []
        plan["status"] = "completed"
        plan["updated_from"] = "conversation_manager_timer"
        completion_update = {
            "origin": "conversation_manager_timer",
            "operation": "complete",
            "current_node_id": "close_conversation",
        }
        timeline = list(plan.get("timeline", [])) if isinstance(plan.get("timeline"), list) else []
        timeline.append(
            {
                "at_utc": now,
                "version": int(plan.get("version", 1) or 1),
                "status": "completed",
                "current_node_id": "close_conversation",
                "next_node_ids": [],
                "update": completion_update,
            }
        )
        plan["timeline"] = timeline[-40:]

        snapshot_plan = {
            "plan_id": str(plan.get("plan_id", "")),
            "version": int(plan.get("version", 1) or 1),
            "status": "completed",
            "mode": str(plan.get("mode", "strict_collections")),
            "objective": str(plan.get("objective", "")),
            "root_node_id": str(plan.get("root_node_id", "")),
            "current_node_id": "close_conversation",
            "previous_node_id": plan.get("previous_node_id"),
            "next_node_ids": [],
            "nodes": [dict(node) for node in nodes],
            "edges": [dict(edge) for edge in plan.get("edges", []) if isinstance(edge, dict)],
            "step_markers": dict(markers),
            "updated_from": "conversation_manager_timer",
            "last_response_target": str(plan.get("last_response_target", "")),
        }
        snapshots_raw = plan.get("timeline_snapshots")
        snapshots = list(snapshots_raw) if isinstance(snapshots_raw, list) else []
        snapshots.append(
            {
                "at_utc": now,
                "version": int(plan.get("version", 1) or 1),
                "status": "completed",
                "current_node_id": "close_conversation",
                "update": dict(completion_update),
                "plan": snapshot_plan,
            }
        )
        plan["timeline_snapshots"] = snapshots[-80:]

    memory.set_state(
        active_conversation_plan=plan or memory_state.get("active_conversation_plan"),
        conversation_complete=True,
        conversation_closing=False,
        conversation_closed=True,
        terminate_call=False,
    )


def is_provider_rate_limit_error(error_text: str) -> bool:
    lowered = str(error_text or "").lower()
    return (
        "rate limit" in lowered
        or "rate_limit_exceeded" in lowered
        or "error code: 429" in lowered
        or "tokens per day" in lowered
        or "tpm" in lowered
    )


def truncate_text(text: str, max_chars: int) -> str:
    value = str(text or "")
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def json_compact(value: Any, *, max_chars: int) -> str:
    raw = json.dumps(value, ensure_ascii=True, default=str, separators=(",", ":"))
    if len(raw) <= max_chars:
        return raw
    return truncate_text(raw, max_chars)


def compact_existing_plan_for_prompt(plan: dict[str, Any], *, minimal: bool = False) -> dict[str, Any]:
    if not isinstance(plan, dict):
        return {}
    nodes_raw = plan.get("nodes") if isinstance(plan.get("nodes"), list) else []
    edges_raw = plan.get("edges") if isinstance(plan.get("edges"), list) else []
    markers = plan.get("step_markers") if isinstance(plan.get("step_markers"), dict) else {}
    max_nodes = 6 if minimal else 10
    max_edges = 10 if minimal else 16
    nodes: list[dict[str, Any]] = []
    for node in nodes_raw[:max_nodes]:
        if not isinstance(node, dict):
            continue
        nodes.append(
            {
                "id": str(node.get("id", "")).strip(),
                "label": str(node.get("label", "")).strip(),
                "status": str(node.get("status", "")).strip(),
                "owner": str(node.get("owner", "")).strip(),
            }
        )
    edges: list[dict[str, Any]] = []
    for edge in edges_raw[:max_edges]:
        if not isinstance(edge, dict):
            continue
        edges.append(
            {
                "from": str(edge.get("from", "")).strip(),
                "to": str(edge.get("to", "")).strip(),
                "condition": str(edge.get("condition", "")).strip(),
            }
        )
    marker_view: dict[str, str] = {}
    marker_limit = 8 if minimal else 14
    for key, raw in markers.items():
        if len(marker_view) >= marker_limit:
            break
        if not isinstance(raw, dict):
            continue
        marker_view[str(key)] = str(raw.get("state", "pending")).strip()
    return {
        "plan_id": str(plan.get("plan_id", "")).strip(),
        "version": int(plan.get("version", 1) or 1),
        "status": str(plan.get("status", "active")).strip(),
        "mode": str(plan.get("mode", "strict_collections")).strip(),
        "current_node_id": str(plan.get("current_node_id", "")).strip(),
        "previous_node_id": str(plan.get("previous_node_id", "")).strip(),
        "next_node_ids": [str(x).strip() for x in (plan.get("next_node_ids") or []) if str(x).strip()][:6],
        "nodes": nodes,
        "edges": edges,
        "step_markers": marker_view,
    }


def compact_memory_state_for_prompt(memory_state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(memory_state, dict):
        return {}
    return {
        "active_case_id": str(memory_state.get("active_case_id", "")).strip(),
        "active_user_id": str(memory_state.get("active_user_id", "")).strip(),
        "active_customer_name": str(memory_state.get("active_customer_name", "")).strip(),
        "identity_verified": bool(memory_state.get("identity_verified", False)),
        "verification_entities": memory_state.get("verification_entities", {}),
        "verification_missing_fields": memory_state.get("verification_missing_fields", []),
        "mode": str(memory_state.get("mode", "strict_collections")).strip(),
        "conversation_mode": str(memory_state.get("conversation_mode", "collections")).strip(),
        "negotiation_stage": str(memory_state.get("negotiation_stage", "none")).strip(),
        "customer_payment_posture": str(memory_state.get("customer_payment_posture", "unknown")).strip(),
        "customer_payment_capacity": memory_state.get("customer_payment_capacity"),
        "customer_payment_capacity_pct": memory_state.get("customer_payment_capacity_pct"),
        "discount_stage": str(memory_state.get("discount_stage", "none")).strip(),
        "customer_payment_willingness": memory_state.get("customer_payment_willingness"),
        "hardship_context": memory_state.get("hardship_context", {}),
        "discount_requested": bool(memory_state.get("discount_requested", False)),
        "discount_offered": bool(memory_state.get("discount_offered", False)),
        "discount_accepted": bool(memory_state.get("discount_accepted", False)),
        "discount_rejected": bool(memory_state.get("discount_rejected", False)),
        "counter_offer_present": bool(memory_state.get("counter_offer_present", False)),
        "customer_profile_summary": memory_state.get("customer_profile_summary", {}),
        "payment_history_summary": memory_state.get("payment_history_summary", {}),
        "offer_history_summary": memory_state.get("offer_history_summary", {}),
        "last_response_target": str(memory_state.get("last_response_target", "")).strip(),
    }
