"""Collection-specific response node with target routing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from agents.collection_agent.llm_structured import StructuredOutputRunner
from agents.collection_agent.nodes.plan_proposal_utils import mark_confirmation_delivered
from src.nodes.response_node import ResponseNode
from src.nodes.types import AgentState, NodeUpdate


class _ResponsePayload(BaseModel):
    message: str
    response_target: str = "customer"


class _CompiledResponseDirectivePayload(BaseModel):
    template_id: str = "safe_follow_up"
    response_target: str = "customer"
    tone: str = "informational"
    render_variables: dict[str, Any] = Field(default_factory=dict)
    response_constraints: dict[str, Any] = Field(default_factory=dict)
    fallback_template_id: str = "safe_follow_up"


@dataclass(slots=True)
class CollectionResponseNode(ResponseNode):
    """Emits response text and a response target for next-hop routing.

    State Keys Read:
    - `user_input`
    - `greeted`
    - `response_target`
    - `plan_proposal`
    - `conversation_plan`
    - `observations`
    - `observation` (latest compatibility mirror)
    - `verification_*` keys (`identity_verified`, `verification_entities`, `verification_missing_fields`)
    - `extracted_entities`
    - `extracted_entities_turn`
    - `extracted_entity_descriptions`
    - `memory` (reads/writes `memory.state`, including conversation history and last response fields)

    State Keys Write:
    - `response`
    - `response_target`
    - `greeted`
    - `conversation_history`
    - `prompt`
    - `system_prompt`
    - `llm_response`
    - `llm_error`
    - `fallback_reason` (optional)
    """

    default_target: str = "customer"
    render_system_prompt: str = ""
    render_user_prompt: str = ""
    verification_opening_template: str = ""
    verification_followup_template: str = ""
    verification_default_missing_text: str = "your date of birth (YYYY-MM-DD) and your registered phone number"
    verification_hardship_prefix: str = "I am sorry to hear this, and I appreciate you sharing it. "
    verification_ack_template: str = "Thank you{customer_suffix}. "
    strict_llm_mode: bool = True
    max_prompt_chars: int = 4200
    max_json_chars: int = 800
    recent_conversation_turns: int = 3
    last_render_debug: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    _DETERMINISTIC_TEMPLATE_IDS = frozenset({
        "wrong_party_privacy_notice",
        "wrong_party_callback_request",
        "wrong_party_callback_clarification",
        "wrong_party_callback_confirmation",
        "wrong_party_callback_revision_confirmation",
        "wrong_party_closing_acknowledgement",
        "conversation_closing",
        "purpose_disclosure",
        "hardship_hold_offer",
        "hardship_hold_confirmation",
        "hardship_hold_closing",
        "human_escalation_pending",
        "human_transfer_pending",
        "installment_discount_offer",
        "installment_discount_confirmation",
        "installment_discount_closing",
        "partial_payment_confirmation",
        "partial_payment_closing",
        "full_payment_link_offer",
        "full_payment_confirmation",
        "full_payment_closing",
    })

    def execute(self, state: AgentState) -> NodeUpdate:
        self.last_render_debug = {
            "prompt": None,
            "system_prompt": None,
            "llm_response": None,
            "llm_error": None,
            "response_render_debug": None,
        }
        plan = state.get("plan_proposal") if isinstance(state.get("plan_proposal"), dict) else {}
        if plan:
            update: NodeUpdate = {"response": self._render_from_proposal(state=state, proposal=plan)}
            plan_target = str(plan.get("target", "")).strip().lower()
            if plan_target:
                update["response_target"] = plan_target
        else:
            update = ResponseNode.execute(self, state)

        target = str(update.get("response_target", state.get("response_target", self.default_target))).strip().lower()
        if target not in {"customer", "self", "discount_planning_agent"}:
            target = self.default_target
        update["response_target"] = target
        update["prompt"] = self.last_render_debug.get("prompt")
        update["system_prompt"] = self.last_render_debug.get("system_prompt")
        update["llm_response"] = self.last_render_debug.get("llm_response")
        update["llm_error"] = self.last_render_debug.get("llm_error")
        update["response_render_debug"] = self.last_render_debug.get("response_render_debug")
        directive = plan.get("response_directive") if isinstance(plan.get("response_directive"), dict) else {}
        objective = str(directive.get("conversation_objective", "")).strip().lower()
        if objective in {
            "wrong_party_callback_confirmation",
            "wrong_party_callback_revision_confirmation",
            "wrong_party_closing_acknowledgement",
            "hardship_hold_closing",
            "installment_discount_closing",
            "partial_payment_closing",
            "full_payment_closing",
        }:
            update["conversation_complete"] = False
            update["conversation_closing"] = True
            update["terminate_call"] = True
            update["termination_grace_seconds"] = 3.0
        if self.last_render_debug.get("fallback_reason"):
            update["fallback_reason"] = self.last_render_debug.get("fallback_reason")
        memory = state.get("memory")
        if memory is not None:
            memory_state = dict(getattr(memory, "state", {}))
            if objective in {
                "hardship_hold_confirmation",
                "installment_discount_confirmation",
                "partial_payment_confirmation",
                "full_payment_confirmation",
            } and str(update.get("response", "")).strip():
                advanced_plan = mark_confirmation_delivered(memory)
                if advanced_plan:
                    update["conversation_plan"] = advanced_plan
            opening_rendered = (
                str(self.last_render_debug.get("response_render_debug", {}).get("template_selected", "")).strip()
                == "verification_request"
                and int(memory_state.get("turn_index", 0) or 0) <= 0
                and not bool(memory_state.get("greeted", False))
                and not bool(memory_state.get("identity_verified", False))
            )
            if opening_rendered:
                memory.set_state(
                    right_party_status="awaiting_confirmation",
                    wrong_party_callback_stage=None,
                    wrong_party_callback_time=None,
                )
            if bool(update.get("conversation_complete", False)):
                memory.set_state(
                    conversation_complete=False,
                    conversation_closing=True,
                    conversation_closed=False,
                    terminate_call=True,
                    termination_grace_seconds=float(update.get("termination_grace_seconds", 3.0)),
                )
        self._update_conversation_history_memory(state=state, update=update)
        return update

    def _update_conversation_history_memory(self, *, state: AgentState, update: NodeUpdate) -> None:
        memory = state.get("memory")
        if memory is None:
            return
        memory_state = dict(getattr(memory, "state", {}))
        history = list(memory_state.get("conversation_history", [])) if isinstance(memory_state.get("conversation_history"), list) else []

        user_text = str(state.get("user_input", "")).strip()
        source = str(state.get("message_source", "customer")).strip().lower() or "customer"
        if user_text and source not in {"self", "system"}:
            if not history or not (
                isinstance(history[-1], dict)
                and str(history[-1].get("role", "")).strip().lower() == source
                and str(history[-1].get("content", "")).strip() == user_text
            ):
                history.append({"role": source, "content": user_text})

        response_text = str(update.get("response", "")).strip()
        response_target = str(update.get("response_target", "customer")).strip().lower()
        if response_text and response_target == "customer":
            if not history or not (
                isinstance(history[-1], dict)
                and str(history[-1].get("role", "")).strip().lower() == "agent"
                and str(history[-1].get("content", "")).strip() == response_text
            ):
                history.append({"role": "agent", "content": response_text})

        # Keep bounded in memory.
        history = history[-40:]
        greeted = bool(memory_state.get("greeted", False)) or bool(response_text and response_target == "customer")
        memory.set_state(conversation_history=history, greeted=greeted)
        update["conversation_history"] = history
        update["greeted"] = greeted

    def route(self, state: AgentState) -> str:
        target = str(state.get("response_target", self.default_target)).strip().lower()
        if target not in {"customer", "self", "discount_planning_agent"}:
            return self.default_target
        return target

    def _render_from_proposal(self, *, state: AgentState, proposal: dict[str, Any]) -> str:
        render_context = self._resolve_render_context(state=state, proposal=proposal)
        directive = self._resolve_response_directive(
            state=state,
            proposal=proposal,
            context=render_context,
        )
        render_debug = self._build_response_render_debug(
            directive=directive,
            response_target=str(directive.get("response_target", render_context.get("response_target", "customer"))).strip().lower()
            or "customer",
        )
        response_target = str(directive.get("response_target", render_context.get("response_target", "customer"))).strip().lower() or "customer"
        if response_target == "discount_planning_agent":
            render_debug["renderer_fallback_used"] = True
            self.last_render_debug["response_render_debug"] = render_debug
            return self._fallback_from_directive(
                directive=directive,
                context=render_context,
                response_target=response_target,
            )
        if self._should_prefer_deterministic_template(directive=directive, context=render_context):
            render_debug["renderer_fallback_used"] = True
            render_debug["policy_filters_applied"] = ["deterministic_compliance_template"]
            self.last_render_debug["response_render_debug"] = render_debug
            return self._fallback_from_directive(
                directive=directive,
                context=render_context,
                response_target=response_target,
            )

        if self.llm is not None:
            llm_response = self._llm_render_from_proposal(
                state=state,
                proposal=proposal,
                render_context=render_context,
                response_directive=directive,
            )
            if llm_response:
                validation = self._validate_response_against_directive(
                    text=llm_response,
                    directive=directive,
                    context=render_context,
                )
                render_debug["policy_filters_applied"] = validation["policy_filters_applied"]
                render_debug["forbidden_actions_blocked"] = validation["forbidden_actions_blocked"]
                if validation["text"]:
                    render_debug["renderer_fallback_used"] = False
                    self.last_render_debug["response_render_debug"] = render_debug
                    return self._apply_minimal_safety_cleanup(
                        text=validation["text"],
                        context=render_context,
                        directive=directive,
                    )
                self.last_render_debug["fallback_reason"] = "directive_validation_failed"
            else:
                render_debug["policy_filters_applied"] = ["llm_render_attempt"]
            if self.strict_llm_mode:
                fallback_reason = str(self.last_render_debug.get("fallback_reason", "")).strip()
                if fallback_reason == "provider_rate_limit":
                    raise RuntimeError(
                        "CollectionResponseNode rate-limited by provider while strict_llm_mode is enabled. "
                        f"Underlying error: {self.last_render_debug.get('llm_error', 'unknown')}"
                    )
        render_debug["renderer_fallback_used"] = True
        self.last_render_debug["response_render_debug"] = render_debug
        return self._fallback_from_directive(
            directive=directive,
            context=render_context,
            response_target=response_target,
        )

    def _should_prefer_deterministic_template(self, *, directive: dict[str, Any], context: dict[str, Any]) -> bool:
        del context
        template_id = str(directive.get("template_id", "")).strip()
        return template_id in self._DETERMINISTIC_TEMPLATE_IDS

    def _resolve_render_context(self, *, state: AgentState, proposal: dict[str, Any]) -> dict[str, Any]:
        memory = state.get("memory")
        memory_state = dict(getattr(memory, "state", {})) if memory is not None else {}
        user_input = str(state.get("user_input", ""))
        response_target = str(proposal.get("target", state.get("response_target", "customer"))).strip().lower() or "customer"
        conversation_plan = (
            proposal.get("conversation_plan")
            if isinstance(proposal.get("conversation_plan"), dict)
            else (state.get("conversation_plan") if isinstance(state.get("conversation_plan"), dict) else {})
        )
        facts = self._resolve_case_facts(state=state, proposal=proposal)
        current_plan_node_id = (
            str(conversation_plan.get("current_node_id", "")).strip()
            if isinstance(conversation_plan, dict)
            else ""
        )
        verification_context = self._build_verification_context(
            state=state,
            memory_state=memory_state,
            proposal=proposal,
        )
        conversation_history = (
            list(state.get("conversation_history", []))
            if isinstance(state.get("conversation_history"), list)
            else (
                list(memory_state.get("conversation_history", []))
                if isinstance(memory_state.get("conversation_history"), list)
                else []
            )
        )
        return {
            "memory_state": memory_state,
            "user_input": user_input,
            "greeted": bool(state.get("greeted", memory_state.get("greeted", False))),
            "response_target": response_target,
            "facts": facts,
            "verification_context": verification_context,
            "observations": state.get("observations") if isinstance(state.get("observations"), list) else [],
            "observation": state.get("observation"),
            "conversation_history": conversation_history,
            "recent_conversation": self._recent_conversation(history=conversation_history),
            "plan_proposal": proposal,
            "conversation_plan": conversation_plan,
            "current_plan_node_id": current_plan_node_id,
        }

    def _resolve_response_directive(
        self,
        *,
        state: AgentState,
        proposal: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        raw_compiled_directive = proposal.get("compiled_response_directive")
        if isinstance(raw_compiled_directive, dict):
            directive = self._normalize_compiled_response_directive(raw_compiled_directive)
            if directive is not None:
                return directive

        raw_legacy_directive = proposal.get("response_directive")
        if not isinstance(raw_legacy_directive, dict):
            raw_legacy_directive = {
                "conversation_objective": proposal.get("conversation_objective"),
                "dialogue_action": proposal.get("dialogue_action"),
                "response_mode": proposal.get("response_mode"),
                "customer_facing_goal": proposal.get("customer_facing_goal"),
                "handoff_target": proposal.get("handoff_target"),
                "draft_response": proposal.get("draft_response"),
            }
        raw_legacy_directive = {key: value for key, value in raw_legacy_directive.items() if value is not None}
        directive = self._compile_legacy_response_directive(
            raw_directive=raw_legacy_directive,
            proposal=proposal,
            context=context,
        )
        if directive is not None:
            return directive
        return self._safe_renderer_fallback_directive(
            state=state,
            proposal=proposal,
            context=context,
        )

    @staticmethod
    def _normalize_compiled_response_directive(raw_directive: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(raw_directive, dict) or not raw_directive:
            return None
        try:
            payload = _CompiledResponseDirectivePayload.model_validate(raw_directive)
        except Exception:
            return None
        directive = payload.model_dump(mode="json")
        directive["template_id"] = str(directive.get("template_id", "")).strip()
        directive["response_target"] = str(directive.get("response_target", "customer")).strip().lower() or "customer"
        directive["tone"] = str(directive.get("tone", "informational")).strip().lower() or "informational"
        directive["fallback_template_id"] = str(directive.get("fallback_template_id", "")).strip() or directive["template_id"]
        if directive["template_id"] == "":
            return None
        return directive

    def _compile_legacy_response_directive(
        self,
        *,
        raw_directive: dict[str, Any],
        proposal: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not isinstance(raw_directive, dict) or not raw_directive:
            return None
        template_id = str(raw_directive.get("template_id", "")).strip() or self._template_id_from_policy_fields(raw_directive)
        if not template_id:
            return None
        response_target = str(
            raw_directive.get("response_target", proposal.get("target", context.get("response_target", "customer")))
        ).strip().lower() or "customer"
        tone = str(raw_directive.get("tone", raw_directive.get("response_mode", "informational"))).strip().lower() or "informational"
        fallback_template_id = str(raw_directive.get("fallback_template_id", "")).strip() or template_id
        render_variables = self._build_render_variables(
            raw_directive=raw_directive,
            proposal=proposal,
            context=context,
        )
        response_constraints = self._build_render_constraints(
            response_target=response_target,
            context=context,
        )
        return self._normalize_compiled_response_directive(
            {
                "template_id": template_id,
                "response_target": response_target,
                "tone": tone,
                "render_variables": render_variables,
                "response_constraints": response_constraints,
                "fallback_template_id": fallback_template_id,
            }
        )

    def _safe_renderer_fallback_directive(
        self,
        *,
        state: AgentState,
        proposal: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        response_target = str(context.get("response_target", "customer")).strip().lower() or "customer"
        verification_context = (
            context.get("verification_context")
            if isinstance(context.get("verification_context"), dict)
            else self._build_verification_context(
                state=state,
                memory_state=context.get("memory_state") if isinstance(context.get("memory_state"), dict) else {},
                proposal=proposal,
            )
        )
        if response_target == "discount_planning_agent":
            return self._normalize_compiled_response_directive(
                {
                    "template_id": "handoff_payload",
                    "response_target": "discount_planning_agent",
                    "tone": "firm",
                    "render_variables": {
                        "message_hint": "Prepare specialist handoff payload and wait for discount recommendation.",
                    },
                    "response_constraints": self._build_render_constraints(
                        response_target="discount_planning_agent",
                        context=context,
                    ),
                    "fallback_template_id": "handoff_payload",
                }
            ) or {}
        if not bool(verification_context.get("identity_verified", False)):
            return self._normalize_compiled_response_directive(
                {
                    "template_id": "verification_request",
                    "response_target": response_target,
                    "tone": "compliance",
                    "render_variables": self._build_render_variables(
                        raw_directive={},
                        proposal=proposal,
                        context=context,
                    ),
                    "response_constraints": self._build_render_constraints(
                        response_target=response_target,
                        context=context,
                    ),
                    "fallback_template_id": "verification_request",
                }
            ) or {}
        return self._normalize_compiled_response_directive(
            {
                "template_id": "safe_follow_up",
                "response_target": response_target,
                "tone": "informational",
                "render_variables": {
                    "customer_facing_goal": "Please let me know how you would like to proceed.",
                },
                "response_constraints": self._build_render_constraints(
                    response_target=response_target,
                    context=context,
                ),
                "fallback_template_id": "safe_follow_up",
            }
        ) or {}

    @staticmethod
    def _template_id_from_policy_fields(raw_directive: dict[str, Any]) -> str:
        objective = str(raw_directive.get("conversation_objective", "")).strip().lower()
        action = str(raw_directive.get("dialogue_action", "")).strip().lower()
        if action == "ask_verification" or objective == "collect_verification":
            return "verification_request"
        if objective == "wrong_party_privacy_notice" or action == "wrong_party_privacy_notice":
            return "wrong_party_privacy_notice"
        if objective == "wrong_party_callback_request" or action == "wrong_party_callback_request":
            return "wrong_party_callback_request"
        if objective == "wrong_party_callback_clarification" or action == "wrong_party_callback_clarification":
            return "wrong_party_callback_clarification"
        if objective == "wrong_party_callback_confirmation" or action == "wrong_party_callback_confirmation":
            return "wrong_party_callback_confirmation"
        if (
            objective == "wrong_party_callback_revision_confirmation"
            or action == "wrong_party_callback_revision_confirmation"
        ):
            return "wrong_party_callback_revision_confirmation"
        if objective == "wrong_party_closing_acknowledgement" or action == "wrong_party_closing_acknowledgement":
            return "wrong_party_closing_acknowledgement"
        if objective == "close_conversation" or action == "close_conversation":
            return "conversation_closing"
        if objective == "purpose_disclosure" or action == "disclose_call_purpose":
            return "purpose_disclosure"
        if objective == "hardship_hold_offer" or action == "offer_hardship_hold":
            return "hardship_hold_offer"
        if objective == "hardship_hold_confirmation" or action == "confirm_hardship_hold":
            return "hardship_hold_confirmation"
        if objective == "hardship_hold_closing" or action == "close_hardship_hold_conversation":
            return "hardship_hold_closing"
        if objective == "hardship_human_escalation" or action == "queue_human_escalation":
            return "human_escalation_pending"
        if objective == "human_transfer_pending" or action == "confirm_live_human_transfer":
            return "human_transfer_pending"
        if objective == "installment_discount_offer" or action == "offer_installment_discount":
            return "installment_discount_offer"
        if objective == "installment_discount_confirmation" or action == "confirm_installment_discount":
            return "installment_discount_confirmation"
        if objective == "installment_discount_closing" or action == "close_installment_discount_conversation":
            return "installment_discount_closing"
        if objective == "partial_payment_amount_request" or action == "ask_partial_payment_amount":
            return "partial_payment_amount_request"
        if objective == "partial_payment_link_offer" or action == "offer_partial_payment_link":
            return "partial_payment_link_offer"
        if objective == "partial_payment_confirmation" or action == "confirm_partial_payment_link":
            return "partial_payment_confirmation"
        if objective == "partial_payment_closing" or action == "close_partial_payment_conversation":
            return "partial_payment_closing"
        if objective == "full_payment_link_offer" or action == "offer_full_payment_link":
            return "full_payment_link_offer"
        if objective == "full_payment_confirmation" or action == "confirm_full_payment_link":
            return "full_payment_confirmation"
        if objective == "full_payment_closing" or action == "close_full_payment_conversation":
            return "full_payment_closing"
        if action == "ask_affordable_amount" or objective == "assess_affordability":
            return "capacity_question"
        if action in {"present_offer", "discuss_arrangement"} or objective in {
            "present_arrangement_options",
            "negotiate_installment",
        }:
            return "arrangement_discussion"
        if action in {"ask_commitment_date", "confirm_payment_intent"} or objective in {
            "confirm_commitment",
            "capture_promise",
        }:
            return "commitment_confirmation"
        if objective == "explain_dues" or action == "present_due_amount":
            return "dues_explanation"
        if objective == "handoff_to_offer_agent" or action == "handoff":
            return "handoff_payload"
        return "safe_follow_up"

    def _build_response_render_debug(
        self,
        *,
        directive: dict[str, Any],
        response_target: str,
    ) -> dict[str, Any]:
        return {
            "template_selected": str(directive.get("template_id", "")).strip(),
            "fallback_template_id": str(directive.get("fallback_template_id", "")).strip(),
            "response_mode": str(directive.get("tone", "")).strip(),
            "response_target": response_target,
            "policy_filters_applied": [],
            "forbidden_actions_blocked": [],
            "renderer_fallback_used": False,
        }

    def _llm_render_from_proposal(
        self,
        *,
        state: AgentState,
        proposal: dict[str, Any],
        render_context: dict[str, Any] | None = None,
        response_directive: dict[str, Any] | None = None,
    ) -> str | None:
        context = dict(render_context) if isinstance(render_context, dict) else self._resolve_render_context(state=state, proposal=proposal)
        memory_state = dict(context.get("memory_state", {})) if isinstance(context.get("memory_state"), dict) else {}
        user_input = str(context.get("user_input", ""))
        observation = context.get("observation")
        if observation is None:
            observations = context.get("observations")
            if isinstance(observations, list):
                for item in reversed(observations):
                    if isinstance(item, dict):
                        observation = item
                        break
        response_target = str(context.get("response_target", "customer")).strip().lower() or "customer"
        facts = context.get("facts") if isinstance(context.get("facts"), dict) else self._resolve_case_facts(state=state, proposal=proposal)
        recent_conversation = (
            list(context.get("recent_conversation", []))
            if isinstance(context.get("recent_conversation"), list)
            else []
        )
        verification_context_merged = self._build_verification_context(state=state, memory_state=memory_state, proposal=proposal)
        response_directive = (
            dict(response_directive)
            if isinstance(response_directive, dict)
            else self._resolve_response_directive(state=state, proposal=proposal, context=context)
        )
        compact_observation = self._compact_observation(observation)

        system_prompt = (f"{self.system_prompt or ''}\n{self.render_system_prompt or ''}").strip()
        user_prompt = self._render_template(
            self.render_user_prompt,
            {
                "user_input": user_input,
                "response_target": str(response_directive.get("response_target", response_target)).strip().lower() or response_target,
                "recent_conversation_json": self._json_compact(recent_conversation, max_chars=1200),
                "template_id": str(response_directive.get("template_id", "")).strip(),
                "tone": str(response_directive.get("tone", "")).strip(),
                "fallback_template_id": str(response_directive.get("fallback_template_id", "")).strip(),
                "render_variables_json": self._json_compact(
                    response_directive.get("render_variables", {}),
                    max_chars=1200,
                ),
                "response_constraints_json": self._json_compact(
                    response_directive.get("response_constraints", {}),
                    max_chars=700,
                ),
                "verification_context_json": self._json_compact(verification_context_merged, max_chars=600),
                "observation_json": self._json_compact(compact_observation, max_chars=700),
            },
        )
        if len(user_prompt) > self.max_prompt_chars:
            # Second-stage clamp for strict provider token windows.
            user_prompt = self._truncate_text(user_prompt, self.max_prompt_chars)
        self.last_render_debug = {
            "prompt": user_prompt,
            "system_prompt": system_prompt or None,
            "llm_response": None,
            "llm_error": None,
        }
        try:
            payload = StructuredOutputRunner(self.llm, max_retries=4).run(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=_ResponsePayload,
            )
            self.last_render_debug["llm_response"] = payload.model_dump(mode="json")
        except Exception as exc:
            err_text = str(exc)
            self.last_render_debug["llm_error"] = err_text
            if self._is_provider_rate_limit_error(err_text):
                self.last_render_debug["fallback_reason"] = "provider_rate_limit"
                return None
            return None
        response = str(payload.message).strip()
        response_target_payload = str(payload.response_target).strip().lower()
        if response_target_payload in {"customer", "self"}:
            proposal["target"] = response_target_payload
        if not response:
            return None
        return response

    def _build_verification_context(
        self,
        *,
        state: AgentState,
        memory_state: dict[str, Any],
        proposal: dict[str, Any],
    ) -> dict[str, Any]:
        verification_entities = state.get("verification_entities")
        if not isinstance(verification_entities, dict):
            verification_entities = (
                memory_state.get("verification_entities", {})
                if isinstance(memory_state.get("verification_entities"), dict)
                else {}
            )
        required = memory_state.get("active_verification_required_fields")
        required_fields = [str(x).strip().lower() for x in required if str(x).strip()] if isinstance(required, list) else []
        if not required_fields:
            required_fields = ["dob", "phone"]
        missing_raw = state.get("verification_missing_fields")
        if not isinstance(missing_raw, list):
            missing_raw = memory_state.get("verification_missing_fields")
        missing_fields = (
            [str(x).strip().lower() for x in missing_raw if str(x).strip()]
            if isinstance(missing_raw, list)
            else [field for field in required_fields if not str(verification_entities.get(field, "")).strip()]
        )
        verified_raw = state.get("verification_verified_fields")
        if not isinstance(verified_raw, list):
            verified_raw = memory_state.get("verification_verified_fields")
        verified_fields = (
            [str(x).strip().lower() for x in verified_raw if str(x).strip()]
            if isinstance(verified_raw, list)
            else [field for field in required_fields if field not in missing_fields]
        )
        label_map = {
            "dob": "your date of birth (YYYY-MM-DD)",
            "phone": "your registered phone number",
            "email": "your registered email address",
            "zip": "your registered zip/pincode",
            "last4_pan": "the last 4 characters of your PAN",
        }
        missing_field_labels = [label_map.get(field, field.replace("_", " ")) for field in missing_fields]
        identity_verified = bool(state.get("identity_verified", memory_state.get("identity_verified", False)))
        verification_incomplete = (not identity_verified) or bool(missing_fields)
        return {
            "identity_verified": identity_verified,
            "required_fields": required_fields,
            "verification_entities": verification_entities,
            "verification_missing_fields": missing_fields,
            "missing_field_labels": missing_field_labels,
            "missing_fields_human": self._join_human_list(missing_field_labels),
            "verification_verified_fields": verified_fields,
            "verification_incomplete": verification_incomplete,
            "current_plan_node_id": str(
                (
                    proposal.get("conversation_plan", {}).get("current_node_id")
                    if isinstance(proposal.get("conversation_plan"), dict)
                    else ""
                )
                or ""
            ).strip(),
        }


    @staticmethod
    def _strip_orchestration_leakage(text: str) -> str:
        cleaned = str(text or "").strip()
        leak_patterns = [
            r"(?i)\bplease wait while i evaluate\b[^\.\!\?]*[\.\!\?]?\s*",
            r"(?i)\bi am processing internal steps\b[^\.\!\?]*[\.\!\?]?\s*",
            r"(?i)\bchecking backend systems\b[^\.\!\?]*[\.\!\?]?\s*",
            r"(?i)\binternal processing\b[^\.\!\?]*[\.\!\?]?\s*",
            r"(?i)\bcontinue internal planning using latest context and determine next execution step\b[^\.\!\?]*[\.\!\?]?\s*",
        ]
        for pattern in leak_patterns:
            cleaned = re.sub(pattern, "", cleaned).strip()
        return cleaned


    def _fallback_from_directive(
        self,
        *,
        directive: dict[str, Any],
        context: dict[str, Any],
        response_target: str,
    ) -> str:
        response_target = str(response_target).strip().lower() or "customer"
        if response_target == "self":
            return "Proceed with the prepared next step."
        if response_target == "discount_planning_agent":
            return "Prepare specialist handoff payload and wait for discount recommendation."

        template_id = str(directive.get("template_id", "safe_follow_up")).strip() or "safe_follow_up"
        render_variables = dict(directive.get("render_variables", {})) if isinstance(directive.get("render_variables"), dict) else {}
        tone = str(directive.get("tone", "informational")).strip().lower() or "informational"
        customer_name = str(render_variables.get("customer_name", "Customer")).strip() or "Customer"
        agent_name = str(render_variables.get("agent_name", "Collections representative")).strip() or "Collections representative"
        company_name = str(render_variables.get("company_name", "the bank")).strip() or "the bank"
        contact_number = str(render_variables.get("contact_number", "")).strip()
        callback_time = str(render_variables.get("callback_time", "")).strip()
        escalation_id = str(render_variables.get("escalation_id", "")).strip()
        missing_fields = str(render_variables.get("missing_fields", self.verification_default_missing_text)).strip()
        overdue_amount_text = str(render_variables.get("overdue_amount_text", "0.00")).strip() or "0.00"
        customer_facing_goal = str(render_variables.get("customer_facing_goal", "")).strip()
        message_hint = str(render_variables.get("message_hint", "")).strip()
        policy_options_text = str(
            render_variables.get("policy_options_text", "a payment arrangement based on the account policy")
        ).strip()
        policy_number = str(render_variables.get("policy_number", "")).strip()
        due_date = str(render_variables.get("due_date", "")).strip()
        reference_number = str(render_variables.get("reference_number", "")).strip()
        installment_amount_text = str(
            render_variables.get("installment_amount_text", overdue_amount_text)
        ).strip()
        hold_months = int(render_variables.get("hold_months", 0) or 0)
        benefits_remain_active = bool(render_variables.get("benefits_remain_active", False))
        confirmation_sla_hours = int(render_variables.get("confirmation_sla_hours", 24) or 24)
        sms_confirmation_sent = bool(render_variables.get("sms_confirmation_sent", False))
        email_confirmation_sent = bool(render_variables.get("email_confirmation_sent", False))
        discount_pct_text = str(render_variables.get("discount_pct_text", "0")).strip() or "0"
        original_amount_text = str(
            render_variables.get("original_amount_text", overdue_amount_text)
        ).strip() or overdue_amount_text
        revised_amount_text = str(render_variables.get("revised_amount_text", "0.00")).strip() or "0.00"
        review_after_months = int(render_variables.get("review_after_months", 3) or 3)
        partial_payment_amount_text = str(
            render_variables.get("partial_payment_amount_text", "0.00")
        ).strip() or "0.00"
        remaining_balance_text = str(
            render_variables.get("remaining_balance_text", "0.00")
        ).strip() or "0.00"
        opening_turn = bool(render_variables.get("opening_turn", False))

        if template_id == "verification_request":
            prefix = self.verification_hardship_prefix if tone == "empathetic" else ""
            if opening_turn:
                template = self.verification_opening_template or (
                    "Hello. This is {agent_name} calling on behalf of {company_name}. "
                    "This call may be recorded for quality and training purposes. "
                    "May I please speak with {customer_name}?"
                )
                return self._render_template(
                    template,
                    {
                        "agent_name": agent_name,
                        "company_name": company_name,
                        "customer_name": customer_name,
                    },
                ).strip()
            template = self.verification_followup_template or (
                "{hardship_prefix}Thank you. For your privacy and security, and before I share any account details, "
                "could you please confirm {missing_human}?"
            )
            return self._render_template(
                template,
                {
                    "hardship_prefix": prefix,
                    "missing_human": missing_fields,
                    "customer_name": customer_name,
                },
            ).strip()
        if template_id == "wrong_party_privacy_notice":
            return (
                f"Thank you. For privacy reasons, I can only discuss this directly with {customer_name}. "
                "I am unable to share any details with anyone else. When would be a good time to try again? "
            ).strip()
        if template_id == "wrong_party_callback_request":
            contact_sentence = (
                f"They can also reach {company_name} at {contact_number} at their convenience. "
                if contact_number
                else ""
            )
            return (
                f"I am unable to share what the call is about, but please let {customer_name} know that "
                f"{company_name} called and would like to speak with them. "
                f"{contact_sentence}"
                "When would be a good time to try again?"
            ).strip()
        if template_id == "wrong_party_callback_clarification":
            goal = str(directive.get("customer_facing_goal", "")).lower()
            if "has passed" in goal:
                return "That time has already passed. What later time would work for the callback?"
            return (
                "Of course. What time would be best to try again, for example a specific time "
                "or a part of the day?"
            )
        if template_id == "wrong_party_callback_confirmation":
            timing = f" {callback_time}" if callback_time else ""
            return (
                f"Certainly. I will try to reach {customer_name}{timing}. "
                f"Please let them know that {company_name} called. "
                "Thank you for your help. Have a good day. Goodbye."
            ).strip()
        if template_id == "wrong_party_callback_revision_confirmation":
            timing = f" {callback_time}" if callback_time else ""
            return (
                f"Understood. I will update the callback and try to reach {customer_name}{timing}. "
                "Thank you for letting me know. Goodbye."
            ).strip()
        if template_id == "wrong_party_closing_acknowledgement":
            return "You're welcome. Goodbye."
        if template_id == "conversation_closing":
            return f"Thank you for your time, {customer_name}. Have a good day. Goodbye."
        if template_id == "purpose_disclosure":
            policy_text = f" policy {policy_number}" if policy_number else " policy"
            due_text = f", due on {due_date}," if due_date else ""
            return (
                f"Thank you for confirming. I am calling about your{policy_text}. "
                f"A premium installment of {installment_amount_text}{due_text} is currently overdue. "
                "I wanted to check in and see how I can help."
            ).strip()
        if template_id == "hardship_hold_offer":
            benefit_text = (
                ", with no impact to your policy benefits during that time"
                if benefits_remain_active
                else ""
            )
            return (
                "I am really sorry to hear that, and thank you for letting me know. "
                "The most important thing right now is keeping your cover active while you get back on your feet. "
                f"Given your situation, I can place your premium on hold for up to {hold_months} months"
                f"{benefit_text}. Would that give you some breathing room, and do you think you would "
                "be in a position to resume payments after that?"
            ).strip()
        if template_id == "hardship_hold_confirmation":
            reference_text = (
                f" Your reference number is {reference_number}." if reference_number else ""
            )
            if sms_confirmation_sent and email_confirmation_sent:
                notification_text = " Confirmation has been sent by SMS and email."
            else:
                notification_text = (
                    f" You will receive confirmation within {confirmation_sla_hours} hours."
                )
            return (
                f"I have arranged a {hold_months}-month hold on your installment."
                f"{reference_text}{notification_text} We will reach out a few days before the hold ends "
                "to discuss next steps."
            ).strip()
        if template_id == "hardship_hold_closing":
            return (
                f"Thank you for your time, {customer_name}. Take care, and we wish you all the best. Goodbye."
            ).strip()
        if template_id == "human_escalation_pending":
            return (
                "I understand, and I'm sorry I couldn't find a suitable option for you. "
                "I'll now connect you with one of our specialists, who can review your situation "
                "and assist you further. Please stay on the line while I transfer your call."
            ).strip()
        if template_id == "human_transfer_pending":
            normalized_user = re.sub(r"[^a-z0-9\s]", " ", str(context.get("user_input", "")).lower())
            normalized_user = re.sub(r"\s+", " ", normalized_user).strip()
            if normalized_user in {"sure", "ok", "okay", "thanks", "thank you", "thankyou"}:
                return "Thank you. Please stay on the line while I transfer your call."
            return (
                "I understand, and I'm sorry I couldn't find a suitable option for you. "
                "I'll now connect you with one of our specialists, who can review your situation "
                "and assist you further. Please stay on the line while I transfer your call."
            ).strip()
        if template_id == "installment_discount_offer":
            return (
                "That is completely understandable, and thank you for being honest. "
                f"In that case, I can apply a {discount_pct_text}% discount to this installment, "
                f"bringing the amount down from {original_amount_text} to {revised_amount_text}. "
                "Would that help ease the pressure?"
            ).strip()
        if template_id == "installment_discount_confirmation":
            return (
                f"I have applied the {discount_pct_text}% discount to this installment. "
                f"Your revised amount is {revised_amount_text}, and your reference number is {reference_number}. "
                "Confirmation has been sent by SMS and email. "
                f"We will review your situation again in {review_after_months} months."
            ).strip()
        if template_id == "installment_discount_closing":
            return (
                f"Thank you for your time, {customer_name}. Take care of yourself, and goodbye."
            ).strip()
        if template_id == "partial_payment_amount_request":
            return (
                "That is helpful, and every contribution makes a difference. "
                "How much do you think you could comfortably manage right now?"
            )
        if template_id == "partial_payment_link_offer":
            return (
                f"That works. I can create a secure payment link for {partial_payment_amount_text}. "
                f"After that payment, the remaining balance will be {remaining_balance_text}. "
                "Shall I send the secure link to your registered mobile by SMS?"
            )
        if template_id == "partial_payment_confirmation":
            return (
                f"Done. I have sent a secure payment link for {partial_payment_amount_text} "
                f"to your registered mobile. Your reference number is {reference_number}. "
                f"The remaining balance is {remaining_balance_text}. Once the partial payment is received, "
                "we can agree on a comfortable date for the balance."
            )
        if template_id == "partial_payment_closing":
            return (
                f"Thank you for working with us on this, {customer_name}. Take care, and goodbye."
            )
        if template_id == "full_payment_link_offer":
            if bool(render_variables.get("autopay_setup_requested", False)):
                return (
                    "Absolutely. I will send a secure link to pay the current dues, and on the same link "
                    "you can set up auto-pay so future installments are deducted automatically on the due date. "
                    "That way you will not have to remember each one manually."
                )
            return (
                "Wonderful. I can send you a secure payment link by SMS, or I can guide you "
                "through paying right now, whichever you prefer."
            )
        if template_id == "full_payment_confirmation":
            if bool(render_variables.get("autopay_setup_requested", False)):
                return (
                    "The link is on its way to your registered mobile, "
                    f"and your reference number is {reference_number}. Once you complete the dues and "
                    "confirm the standing instruction, you will receive a confirmation for both."
                )
            return (
                "The link is on its way to your registered mobile. Once payment is received "
                f"you will get an instant receipt, and your reference number is {reference_number}. "
                "Would you also like to set up auto-pay so future installments are never missed?"
            )
        if template_id == "full_payment_closing":
            if bool(render_variables.get("autopay_setup_requested", False)):
                return (
                    f"Great choice, that will save you the hassle going forward. Thank you, {customer_name}. "
                    "Have a wonderful day, goodbye."
                )
            return (
                f"No problem at all. Thank you for taking care of this so quickly, {customer_name}. "
                "Have a great day, and goodbye."
            )
        if template_id == "dues_explanation":
            return (
                f"Thank you {customer_name}. Your overdue amount is INR {overdue_amount_text}. "
                "What would you like to do next to bring the account current?"
            ).strip()
        if template_id == "capacity_question":
            prefix = "I am sorry to hear that. " if tone == "empathetic" else ""
            return (
                f"{prefix}The available standard options include {policy_options_text}. "
                "What amount or payment date would realistically work for you?"
            ).strip()
        if template_id == "arrangement_discussion":
            if bool(render_variables.get("generic_options_after_discount", False)):
                return (
                    "I understand the discount may still not be enough. "
                    f"The other standard options available are {policy_options_text}. "
                    "Would any of these work for you?"
                ).strip()
            return customer_facing_goal or "Let us work toward a practical repayment option. What installment amount would be manageable for you?"
        if template_id == "commitment_confirmation":
            return customer_facing_goal or "Thank you. What amount and payment date can you confidently commit to for the next step?"
        if template_id == "handoff_payload":
            return message_hint or "Prepare specialist handoff payload and wait for discount recommendation."
        return customer_facing_goal or "Please let me know how you would like to proceed."

    def _validate_response_against_directive(
        self,
        *,
        text: str,
        directive: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        rendered = self._apply_minimal_safety_cleanup(text=text, context=context, directive=directive)
        result = {
            "text": None,
            "policy_filters_applied": [
                "minimal_safety_cleanup",
                "placeholder_cleanup",
                "internal_terminology_cleanup",
                "verification_amount_guard",
            ],
            "forbidden_actions_blocked": [],
        }
        if not rendered:
            result["forbidden_actions_blocked"].append("empty_response")
            return result
        if self._contains_unresolved_placeholders(rendered):
            result["forbidden_actions_blocked"].append("unresolved_placeholders")
        verification_context = context.get("verification_context") if isinstance(context.get("verification_context"), dict) else {}
        constraints = directive.get("response_constraints") if isinstance(directive.get("response_constraints"), dict) else {}
        if bool(constraints.get("no_dues_before_verification", False)):
            lowered = rendered.lower()
            if any(token in lowered for token in ["inr ", "overdue", "dues", "amount", "emi", "late fee"]):
                result["forbidden_actions_blocked"].append("disclose_dues_before_verification")
        if bool(constraints.get("wrong_party", False)):
            lowered = rendered.lower()
            if any(
                token in lowered
                for token in [
                    "loan",
                    "policy number",
                    "account number",
                    "case id",
                    "overdue",
                    "dues",
                    "payment",
                    "date of birth",
                    "registered phone",
                ]
            ):
                result["forbidden_actions_blocked"].append("disclose_account_details_to_wrong_party")
        if bool(constraints.get("greeted", False)) and self._contains_repeat_greeting(rendered):
            result["forbidden_actions_blocked"].append("repeat_greeting")
        if bool(constraints.get("avoid_internal_terms", True)) and self._contains_internal_processing(rendered):
            result["forbidden_actions_blocked"].append("mention_internal_processing")
        template_id = str(directive.get("template_id", "")).strip()
        render_variables = (
            directive.get("render_variables")
            if isinstance(directive.get("render_variables"), dict)
            else {}
        )
        lowered = rendered.lower()
        if template_id == "partial_payment_amount_request":
            if "?" not in rendered:
                result["forbidden_actions_blocked"].append("missing_partial_amount_question")
            if any(token in lowered for token in ["link has been sent", "link is on its way", "payment received"]):
                result["forbidden_actions_blocked"].append("premature_partial_payment_claim")
        elif template_id == "partial_payment_link_offer":
            partial_amount = str(render_variables.get("partial_payment_amount_text", "")).strip()
            remaining_balance = str(render_variables.get("remaining_balance_text", "")).strip()
            if partial_amount and partial_amount not in rendered:
                result["forbidden_actions_blocked"].append("missing_partial_payment_amount")
            if remaining_balance and remaining_balance not in rendered:
                result["forbidden_actions_blocked"].append("missing_remaining_balance")
            if any(token in lowered for token in ["link has been sent", "link is on its way", "payment received"]):
                result["forbidden_actions_blocked"].append("premature_partial_payment_claim")
        elif template_id == "hardship_hold_offer":
            hold_months = str(render_variables.get("hold_months", "")).strip()
            if hold_months and hold_months not in rendered:
                result["forbidden_actions_blocked"].append("missing_hold_duration")
            if "discount" in lowered:
                result["forbidden_actions_blocked"].append("mixed_offer_with_discount")
            if any(token in lowered for token in ["hold has been arranged", "hold is active", "confirmation has been sent"]):
                result["forbidden_actions_blocked"].append("premature_hold_claim")
            if "?" not in rendered:
                result["forbidden_actions_blocked"].append("missing_hold_decision_question")
        elif template_id == "installment_discount_offer":
            discount_pct = str(render_variables.get("discount_pct_text", "")).strip()
            original_amount = str(render_variables.get("original_amount_text", "")).strip()
            revised_amount = str(render_variables.get("revised_amount_text", "")).strip()
            for value, reason in (
                (discount_pct, "missing_discount_percentage"),
                (original_amount, "missing_original_amount"),
                (revised_amount, "missing_revised_amount"),
            ):
                if value and value not in rendered:
                    result["forbidden_actions_blocked"].append(reason)
            if "hold" in lowered:
                result["forbidden_actions_blocked"].append("mixed_offer_with_hold")
            if any(token in lowered for token in ["discount has been applied", "confirmation has been sent"]):
                result["forbidden_actions_blocked"].append("premature_discount_claim")
            if "?" not in rendered:
                result["forbidden_actions_blocked"].append("missing_discount_decision_question")
        if result["forbidden_actions_blocked"]:
            return result
        result["text"] = rendered
        return result

    def _apply_minimal_safety_cleanup(
        self,
        *,
        text: str,
        context: dict[str, Any],
        directive: dict[str, Any],
    ) -> str:
        del context, directive
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"```(?:json)?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned)
        cleaned = self._strip_orchestration_leakage(cleaned)
        cleaned = re.sub(r"\[(?:insert\s+)?[^\]]+\]", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _contains_internal_processing(text: str) -> bool:
        lowered = str(text or "").lower()
        return any(
            token in lowered
            for token in [
                "internal processing",
                "backend",
                "workflow",
                "tool call",
                "node",
                "prompt",
                "orchestration",
            ]
        )

    @staticmethod
    def _contains_repeat_greeting(text: str) -> bool:
        lowered = str(text or "").strip().lower()
        return lowered.startswith(("hi ", "hi,", "hello ", "hello,", "good morning", "good afternoon", "good evening"))

    @staticmethod
    def _contains_unresolved_placeholders(text: str) -> bool:
        return bool(re.search(r"\{[^}]+\}|\[[^\]]+\]", str(text or "")))

    @staticmethod
    def _join_human_list(items: list[str]) -> str:
        values = [str(item).strip() for item in items if str(item).strip()]
        if not values:
            return "the required verification details"
        if len(values) == 1:
            return values[0]
        if len(values) == 2:
            return f"{values[0]} and {values[1]}"
        return f"{', '.join(values[:-1])}, and {values[-1]}"

    def _build_render_variables(
        self,
        *,
        raw_directive: dict[str, Any],
        proposal: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        facts = context.get("facts") if isinstance(context.get("facts"), dict) else {}
        memory_state = context.get("memory_state") if isinstance(context.get("memory_state"), dict) else {}
        verification_context = context.get("verification_context") if isinstance(context.get("verification_context"), dict) else {}
        customer_name = str(facts.get("customer_name", memory_state.get("active_customer_name", "Customer"))).strip() or "Customer"
        overdue_amount = float(facts.get("overdue_amount", memory_state.get("active_overdue_amount", 0.0)) or 0.0)
        missing_fields = verification_context.get("missing_fields_human")
        if not missing_fields:
            missing_fields = self._join_human_list(verification_context.get("missing_field_labels", []))
        turn_index = int(memory_state.get("turn_index", 0) or 0)
        greeted = bool(context.get("greeted", False))
        active_context = (
            memory_state.get("active_collection_context")
            if isinstance(memory_state.get("active_collection_context"), dict)
            else {}
        )
        customer = active_context.get("customer") if isinstance(active_context.get("customer"), dict) else {}
        case = active_context.get("case") if isinstance(active_context.get("case"), dict) else {}
        customer_variables = customer.get("variables") if isinstance(customer.get("variables"), dict) else {}
        agent_name = str(
            customer_variables.get("[AGENT_NAME]", case.get("assigned_agent", "Collections representative"))
        ).strip() or "Collections representative"
        company_name = str(customer_variables.get("[COMPANY_NAME]", "the bank")).strip() or "the bank"
        contact_number = str(customer_variables.get("[CONTACT_NUMBER]", "")).strip()
        policy_number = str(customer_variables.get("[POLICY_NUMBER]", case.get("loan_id", ""))).strip()
        due_date = str(customer_variables.get("[DUE_DATE]", "")).strip()
        reference_number = str(
            customer_variables.get("[REF_NUMBER]", memory_state.get("active_case_id", ""))
        ).strip()
        installment_amount = str(
            customer_variables.get("[AMOUNT]", f"{overdue_amount:.2f}")
        ).strip()
        callback_time = str(memory_state.get("wrong_party_callback_time", "") or "").strip()
        policy = active_context.get("policy") if isinstance(active_context.get("policy"), dict) else {}
        hold_program = (
            memory_state.get("hardship_hold_program")
            if isinstance(memory_state.get("hardship_hold_program"), dict)
            else {}
        )
        hold_details = (
            memory_state.get("hardship_hold_details")
            if isinstance(memory_state.get("hardship_hold_details"), dict)
            else {}
        )
        discount_details = (
            memory_state.get("installment_discount_details")
            if isinstance(memory_state.get("installment_discount_details"), dict)
            else {}
        )
        partial_details = (
            memory_state.get("partial_payment_details")
            if isinstance(memory_state.get("partial_payment_details"), dict)
            else {}
        )
        full_payment_details = (
            memory_state.get("full_payment_details")
            if isinstance(memory_state.get("full_payment_details"), dict)
            else {}
        )
        human_escalation_id = str(memory_state.get("human_escalation_id", "") or "").strip()
        return {
            "customer_name": customer_name,
            "agent_name": agent_name,
            "company_name": company_name,
            "contact_number": contact_number,
            "escalation_id": human_escalation_id,
            "policy_number": policy_number,
            "due_date": due_date,
            "reference_number": str(
                discount_details.get(
                    "reference_number",
                    full_payment_details.get(
                        "payment_reference_id",
                        partial_details.get(
                            "payment_reference_id",
                            hold_details.get("reference_number", reference_number),
                        ),
                    ),
                )
            ).strip(),
            "installment_amount_text": installment_amount,
            "hold_months": int(
                hold_details.get("hold_months", hold_program.get("max_hold_months", 0)) or 0
            ),
            "benefits_remain_active": bool(
                hold_details.get(
                    "benefits_remain_active",
                    hold_program.get("benefits_remain_active", False),
                )
            ),
            "confirmation_sla_hours": int(
                hold_details.get(
                    "confirmation_sla_hours",
                    hold_program.get("confirmation_sla_hours", 24),
                )
                or 24
            ),
            "sms_confirmation_sent": (
                isinstance(hold_details.get("sms_confirmation"), dict)
                and str(hold_details.get("sms_confirmation", {}).get("status", "")).strip().lower() == "sent"
            ),
            "email_confirmation_sent": (
                isinstance(hold_details.get("email_confirmation"), dict)
                and str(hold_details.get("email_confirmation", {}).get("status", "")).strip().lower() == "sent"
            ),
            "discount_pct_text": f"{float(discount_details.get('discount_pct', 0) or 0):g}",
            "original_amount_text": f"{float(discount_details.get('original_amount', overdue_amount) or 0):.2f}",
            "revised_amount_text": f"{float(discount_details.get('revised_amount', 0) or 0):.2f}",
            "review_after_months": int(discount_details.get("review_after_months", 3) or 3),
            "partial_payment_amount_text": f"{float(partial_details.get('partial_payment_amount', 0) or 0):.2f}",
            "remaining_balance_text": f"{float(partial_details.get('remaining_balance', 0) or 0):.2f}",
            "full_payment_amount_text": f"{float(full_payment_details.get('amount', overdue_amount) or 0):.2f}",
            "callback_time": callback_time,
            "case_id": str(facts.get("case_id", memory_state.get("active_case_id", "COLL-1001"))).strip() or "COLL-1001",
            "overdue_amount_text": f"{overdue_amount:.2f}",
            "missing_fields": str(missing_fields or self.verification_default_missing_text).strip(),
            "customer_facing_goal": str(raw_directive.get("customer_facing_goal", "")).strip(),
            "message_hint": str(raw_directive.get("draft_response", proposal.get("draft_response", ""))).strip(),
            "policy_options_text": self._policy_options_text(policy),
            "generic_options_after_discount": bool(memory_state.get("generic_options_offered_after_discount", False)),
            "autopay_setup_requested": bool(memory_state.get("autopay_setup_requested", False)),
            "autopay_stage": str(memory_state.get("autopay_stage", "")).strip().lower(),
            "opening_turn": (turn_index <= 0) and not greeted,
        }

    @staticmethod
    def _policy_options_text(policy: dict[str, Any]) -> str:
        options: list[str] = []
        if bool(policy.get("allow_partial_payment", False)):
            minimum_pct = policy.get("min_partial_payment_pct")
            if isinstance(minimum_pct, (int, float)) and float(minimum_pct) > 0:
                options.append(f"a partial payment starting from {float(minimum_pct):g}% of the overdue amount")
            else:
                options.append("a partial payment")
        max_promise_days = policy.get("max_promise_days")
        if isinstance(max_promise_days, (int, float)) and int(max_promise_days) > 0:
            options.append(f"a payment commitment within {int(max_promise_days)} days")
        if bool(policy.get("restructure_allowed", False)):
            options.append("a standard restructure review")
        if not options:
            return "a payment commitment based on the account policy"
        if len(options) == 1:
            return options[0]
        return f"{', '.join(options[:-1])}, or {options[-1]}"

    def _build_render_constraints(
        self,
        *,
        response_target: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        verification_context = context.get("verification_context") if isinstance(context.get("verification_context"), dict) else {}
        return {
            "avoid_internal_terms": True,
            "avoid_placeholders": True,
            "avoid_verbatim_repeat": True,
            "greeted": bool(context.get("greeted", False)),
            "ask_one_question": response_target == "customer",
            "no_dues_before_verification": not bool(verification_context.get("identity_verified", False)),
            "verification_incomplete": bool(verification_context.get("verification_incomplete", False)),
            "wrong_party": str(context.get("memory_state", {}).get("right_party_status", "")).strip().lower()
            == "wrong_party",
        }

    def _recent_conversation(self, *, history: list[Any]) -> list[dict[str, str]]:
        filtered: list[dict[str, str]] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role", "")).strip().lower()
            content = str(item.get("content", "")).strip()
            if role not in {"customer", "agent"} or not content:
                continue
            filtered.append({"role": role, "content": content})
        if not filtered:
            return []
        max_messages = max(1, int(self.recent_conversation_turns or 1)) * 2
        return filtered[-max_messages:]

    @staticmethod
    def _resolve_case_facts(*, state: AgentState, proposal: dict[str, Any]) -> dict[str, Any]:
        memory = state.get("memory")
        memory_state = dict(getattr(memory, "state", {})) if memory is not None else {}
        customer_name = str(memory_state.get("active_customer_name", "Customer")).strip() or "Customer"
        case_id = str(memory_state.get("active_case_id", "COLL-1001")).strip() or "COLL-1001"
        overdue_amount = float(memory_state.get("active_overdue_amount", 0.0) or 0.0)
        emi_amount = float(memory_state.get("active_emi_amount", 0.0) or 0.0)
        late_fee = float(memory_state.get("active_late_fee", 0.0) or 0.0)
        dpd = int(memory_state.get("active_dpd", 0) or 0)

        context = proposal.get("context") if isinstance(proposal.get("context"), dict) else {}
        if context:
            customer_name = str(context.get("customer_name", customer_name)).strip() or customer_name
            case_id = str(context.get("case_id", case_id)).strip() or case_id
            overdue_amount = float(context.get("overdue_amount", overdue_amount) or overdue_amount)

        opening_context = proposal.get("opening_context") if isinstance(proposal.get("opening_context"), dict) else {}
        if opening_context:
            customer_name = str(opening_context.get("customer_name", customer_name)).strip() or customer_name
            case_id = str(opening_context.get("case_id", case_id)).strip() or case_id
            overdue_amount = float(opening_context.get("overdue_amount", overdue_amount) or overdue_amount)

        case_snapshot = proposal.get("case_snapshot") if isinstance(proposal.get("case_snapshot"), dict) else {}
        if case_snapshot:
            customer_name = str(case_snapshot.get("customer_name", customer_name)).strip() or customer_name
            case_id = str(case_snapshot.get("case_id", case_id)).strip() or case_id
            overdue_amount = float(case_snapshot.get("overdue_amount", overdue_amount) or overdue_amount)
            emi_amount = float(case_snapshot.get("emi_amount", emi_amount) or emi_amount)
            late_fee = float(case_snapshot.get("late_fee", late_fee) or late_fee)
            dpd = int(case_snapshot.get("dpd", dpd) or dpd)

        payment_context = proposal.get("payment_context") if isinstance(proposal.get("payment_context"), dict) else {}
        if payment_context:
            customer_name = str(payment_context.get("customer_name", customer_name)).strip() or customer_name
            case_id = str(payment_context.get("case_id", case_id)).strip() or case_id
            overdue_amount = float(payment_context.get("overdue_amount", overdue_amount) or overdue_amount)

        return {
            "customer_name": customer_name,
            "case_id": case_id,
            "overdue_amount": overdue_amount,
            "emi_amount": emi_amount,
            "late_fee": late_fee,
            "dpd": dpd,
        }

    @staticmethod
    def _render_template(template: str, values: dict[str, Any]) -> str:
        rendered = template
        for key, value in values.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))
        return rendered

    @staticmethod
    def _is_provider_rate_limit_error(error_text: str) -> bool:
        lowered = str(error_text or "").lower()
        return (
            "rate limit" in lowered
            or "rate_limit_exceeded" in lowered
            or "error code: 429" in lowered
            or "tokens per day" in lowered
            or "tpm" in lowered
        )

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        value = str(text or "")
        if len(value) <= max_chars:
            return value
        return value[: max_chars - 3].rstrip() + "..."

    def _json_compact(self, value: Any, *, max_chars: int) -> str:
        raw = json.dumps(value, ensure_ascii=True, default=str, separators=(",", ":"))
        if len(raw) <= max_chars:
            return raw
        return self._truncate_text(raw, max_chars)

    @staticmethod
    def _compact_observation(observation: Any) -> dict[str, Any]:
        if not isinstance(observation, dict):
            return {}
        phase = observation.get("tool_phase") if isinstance(observation.get("tool_phase"), dict) else observation
        if not isinstance(phase, dict):
            return {}
        output = phase.get("output") if isinstance(phase.get("output"), dict) else {}
        return {
            "tool_name": str(phase.get("tool_name", "")).strip(),
            "status": str(output.get("status", "")).strip(),
            "needs_additional_action": bool(output.get("needs_additional_action", False)),
            "keys": sorted([str(k) for k in output.keys()])[:12],
        }
