"""Created: 2026-09-26

Purpose: Lets the configured language model plan bounded Chat actions.

This module contains no keyword, regex, or lexical intent classifier. The model
selects the accountable Planet and one or more typed actions from an explicit
allow-list. Code then validates authority and schemas before execution. Invalid
model output is retried through the model and never replaced by a deterministic
intent fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from easy_agents.constellation.commons_runtime import (
    ApprovalDecision,
    ArtifactCreate,
    CalendarProposalCreate,
    ClaimVerificationRequest,
    CommonsRuntime,
    KnowledgeSourceCreate,
    ScheduledReviewCreate,
    VaultId,
    VaultMemoryCreate,
)
from easy_agents.constellation.satellite_tools import (
    LocalSatelliteRuntime,
    PlannedSatelliteCall,
)
from easy_agents.galaxy.enums import LifecycleStatus
from easy_agents.galaxy.registry import GalaxyRegistry
from easy_agents.observability import EntityReference, Severity
from src.tools.math import CalculateInput, UnitConvertInput


ActionName = Literal[
    "respond",
    "calculate",
    "unit_convert",
    "memory_write",
    "memory_search",
    "artifact_create",
    "artifact_list",
    "knowledge_add",
    "knowledge_search",
    "knowledge_summarize",
    "knowledge_verify",
    "review_create",
    "review_list",
    "calendar_propose",
    "calendar_list",
    "approval_list",
    "approval_decide",
    "commons_status",
]

SUPPORTED_ACTIONS: tuple[ActionName, ...] = (
    "respond",
    "calculate",
    "unit_convert",
    "memory_write",
    "memory_search",
    "artifact_create",
    "artifact_list",
    "knowledge_add",
    "knowledge_search",
    "knowledge_summarize",
    "knowledge_verify",
    "review_create",
    "review_list",
    "calendar_propose",
    "calendar_list",
    "approval_list",
    "approval_decide",
    "commons_status",
)


class NaturalLanguagePlanningError(RuntimeError):
    """Raised when the model exhausts bounded plan-generation attempts."""


class _StrictModel(BaseModel):
    """Strict immutable base for model-planning contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class NaturalLanguageAction(_StrictModel):
    """One model-selected action whose arguments are validated separately."""

    action: ActionName
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=400)


class NaturalLanguagePlan(_StrictModel):
    """Bounded multi-action plan and model-selected accountable Planet."""

    circle_id: str = Field(min_length=1, max_length=160)
    planet_id: str = Field(min_length=1, max_length=160)
    actions: tuple[NaturalLanguageAction, ...] = Field(min_length=1, max_length=5)
    reasoning_summary: str = Field(min_length=1, max_length=800)

    @model_validator(mode="after")
    def validate_respond_shape(self) -> "NaturalLanguagePlan":
        """Prevents an advisory-only marker from hiding executable actions."""

        names = [item.action for item in self.actions]
        if "respond" in names and len(names) != 1:
            raise ValueError("respond must be the only action in a plan")
        return self


class PlanningEvidence(_StrictModel):
    """Portable evidence that a model, rather than a rule, selected the plan."""

    planning_id: str
    model_id: str
    attempts: int = Field(ge=1, le=3)
    circle_id: str
    planet_id: str
    action_names: tuple[ActionName, ...]
    duration_ms: float = Field(ge=0)


class PlannedChatTurn(_StrictModel):
    """Validated plan paired with non-content planning evidence."""

    plan: NaturalLanguagePlan
    evidence: PlanningEvidence


class ActionInvocation(_StrictModel):
    """Auditable result of one model-selected, schema-validated local action."""

    action: ActionName
    planet_id: str
    status: Literal["completed"] = "completed"
    arguments: dict[str, Any]
    output: dict[str, Any]
    reason: str


class _EmptyArguments(_StrictModel):
    """Schema for list/status actions that require no parameters."""


class _MemoryWriteArguments(_StrictModel):
    """Natural-language memory write arguments."""

    content: str = Field(min_length=1, max_length=50_000)
    tags: tuple[str, ...] = ()


class _QueryArguments(_StrictModel):
    """Bounded query arguments shared by local search and summaries."""

    query: str = Field(min_length=1, max_length=4_000)
    limit: int = Field(default=10, ge=1, le=100)


class _ReviewListArguments(_StrictModel):
    """Optional Scheduled Review state filter."""

    status: Literal["scheduled", "due", "completed", "cancelled"] | None = None


class _CalendarListArguments(_StrictModel):
    """Safe local calendar projection filter."""

    include_proposed: bool = True


class _ApprovalListArguments(_StrictModel):
    """Optional approval-state filter."""

    status: Literal["pending", "approved", "rejected", "cancelled"] | None = (
        "pending"
    )


class _ApprovalDecisionArguments(ApprovalDecision):
    """Approval identifier paired with the existing decision contract."""

    approval_id: str = Field(min_length=1, max_length=256)


_ARGUMENT_MODELS: dict[ActionName, type[BaseModel]] = {
    "respond": _EmptyArguments,
    "calculate": CalculateInput,
    "unit_convert": UnitConvertInput,
    "memory_write": _MemoryWriteArguments,
    "memory_search": _QueryArguments,
    "artifact_create": ArtifactCreate,
    "artifact_list": _EmptyArguments,
    "knowledge_add": KnowledgeSourceCreate,
    "knowledge_search": _QueryArguments,
    "knowledge_summarize": _QueryArguments,
    "knowledge_verify": ClaimVerificationRequest,
    "review_create": ScheduledReviewCreate,
    "review_list": _ReviewListArguments,
    "calendar_propose": CalendarProposalCreate,
    "calendar_list": _CalendarListArguments,
    "approval_list": _ApprovalListArguments,
    "approval_decide": _ApprovalDecisionArguments,
    "commons_status": _EmptyArguments,
}


class NaturalLanguagePlanner:
    """Uses Gemma to select a Planet and typed actions without rule fallback."""

    def __init__(
        self,
        *,
        llm: Any,
        registry: GalaxyRegistry,
        event_recorder: Any | None = None,
        max_attempts: int = 2,
    ) -> None:
        """Binds one model and registry to a validated planning boundary."""

        if max_attempts < 1 or max_attempts > 3:
            raise ValueError("max_attempts must be between 1 and 3")
        self.llm = llm
        self.registry = registry
        self.event_recorder = event_recorder
        self.max_attempts = max_attempts

    def plan(
        self,
        message: str,
        *,
        vault_id: VaultId,
        mission_id: str,
    ) -> PlannedChatTurn:
        """Requests and validates a model plan, retrying only through the model."""

        planning_id = f"planning-{uuid4().hex}"
        model_id = str(getattr(self.llm, "model_name", type(self.llm).__name__))
        started = perf_counter()
        error_feedback = ""
        for attempt in range(1, self.max_attempts + 1):
            self._record(
                "model.started",
                "Natural-language action planning started",
                "running",
                mission_id=mission_id,
                attributes={
                    "planning_id": planning_id,
                    "model_id": model_id,
                    "call_kind": "action_planning",
                    "attempt": attempt,
                },
            )
            try:
                payload = self._generate_json(
                    self._prompt(
                        message=message,
                        vault_id=vault_id,
                        error_feedback=error_feedback,
                    )
                )
                plan = NaturalLanguagePlan.model_validate(payload)
                plan = self._validate_plan(plan, vault_id=vault_id)
            except Exception as exc:
                error_feedback = self._bounded_error(exc)
                self._record(
                    "model.failed",
                    "Natural-language action plan was invalid",
                    "failed",
                    mission_id=mission_id,
                    severity=Severity.WARNING,
                    attributes={
                        "planning_id": planning_id,
                        "model_id": model_id,
                        "call_kind": "action_planning",
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                    },
                )
                if attempt == self.max_attempts:
                    raise NaturalLanguagePlanningError(
                        "Gemma could not produce a valid authorized action plan after "
                        f"{attempt} attempt(s): {error_feedback}"
                    ) from exc
                continue
            duration_ms = round((perf_counter() - started) * 1000, 3)
            evidence = PlanningEvidence(
                planning_id=planning_id,
                model_id=model_id,
                attempts=attempt,
                circle_id=plan.circle_id,
                planet_id=plan.planet_id,
                action_names=tuple(item.action for item in plan.actions),
                duration_ms=duration_ms,
            )
            self._record(
                "model.completed",
                "Natural-language action plan accepted",
                "completed",
                mission_id=mission_id,
                duration_ms=duration_ms,
                attributes={
                    "planning_id": planning_id,
                    "model_id": model_id,
                    "call_kind": "action_planning",
                    "attempt": attempt,
                    "circle_id": plan.circle_id,
                    "planet_id": plan.planet_id,
                    "action_names": list(evidence.action_names),
                },
            )
            return PlannedChatTurn(plan=plan, evidence=evidence)
        raise AssertionError("unreachable planning loop")

    def _generate_json(self, prompt: str) -> dict[str, Any]:
        """Calls the configured model's JSON completion interface."""

        generate_json = getattr(self.llm, "generate_json", None)
        if not callable(generate_json):
            raise TypeError("The configured model does not implement generate_json().")
        payload = generate_json("", prompt)
        if not isinstance(payload, dict):
            raise TypeError("The model plan must be a JSON object.")
        return payload

    def _validate_plan(
        self, plan: NaturalLanguagePlan, *, vault_id: VaultId
    ) -> NaturalLanguagePlan:
        """Validates argument schemas and the selected Planet's Charter."""

        planet = self.registry.get_planet(plan.planet_id)
        self.registry.get_circle(plan.circle_id)
        if plan.circle_id not in planet.circle_ids:
            raise PermissionError(
                f"Planet {planet.id!r} is not a member of Circle {plan.circle_id!r}."
            )
        if planet.status in {LifecycleStatus.QUARANTINED, LifecycleStatus.RETIRED}:
            raise PermissionError(f"Planet {planet.id!r} cannot accept new Missions.")
        normalized: list[NaturalLanguageAction] = []
        for action in plan.actions:
            arguments = _ARGUMENT_MODELS[action.action].model_validate(
                action.arguments
            ).model_dump(mode="json", exclude_none=True)
            self._validate_authority(
                planet_id=planet.id,
                action=action.action,
                vault_id=vault_id,
            )
            normalized.append(action.model_copy(update={"arguments": arguments}))
        return plan.model_copy(update={"actions": tuple(normalized)})

    def _validate_authority(
        self,
        *,
        planet_id: str,
        action: ActionName,
        vault_id: VaultId,
    ) -> None:
        """Ensures the model-selected Planet declares every required component."""

        planet = self.registry.get_planet(planet_id)
        satellites = set(planet.charter.satellite_ids)
        capabilities = set(planet.charter.capability_ids)
        playbooks = set(planet.charter.playbook_ids)
        gates = set(planet.charter.gate_ids)
        if action in {"memory_write", "memory_search"}:
            required = "memory_write" if action == "memory_write" else "memory_search"
            if required not in satellites or vault_id not in planet.charter.vault_ids:
                raise PermissionError(
                    f"Planet {planet_id!r} lacks {required!r} or Vault {vault_id!r}."
                )
        elif action in {"calculate", "unit_convert"} and action not in satellites:
            raise PermissionError(f"Planet {planet_id!r} lacks Satellite {action!r}.")
        elif action.startswith("knowledge_"):
            capability = {
                "knowledge_add": "knowledge.search",
                "knowledge_search": "knowledge.search",
                "knowledge_summarize": "knowledge.summarize",
                "knowledge_verify": "knowledge.verify_claims",
            }[action]
            if capability not in capabilities:
                raise PermissionError(
                    f"Planet {planet_id!r} lacks capability {capability!r}."
                )
        elif action.startswith("calendar_"):
            capability = (
                "calendar.propose" if action == "calendar_propose" else "calendar.inspect"
            )
            if capability not in capabilities:
                raise PermissionError(
                    f"Planet {planet_id!r} lacks capability {capability!r}."
                )
        elif action.startswith("review_") and "scheduled_review" not in playbooks:
            raise PermissionError(
                f"Planet {planet_id!r} lacks the Scheduled Review Playbook."
            )
        elif action.startswith("artifact_") and planet_id != "digital_librarian":
            raise PermissionError(
                "Artifact actions must be assigned to the Digital Librarian."
            )
        elif action.startswith("approval_") and "outbound_approval" not in gates:
            raise PermissionError(
                f"Planet {planet_id!r} lacks the Outbound Approval Gate."
            )
        elif action == "commons_status" and planet_id != "safety_steward":
            raise PermissionError(
                "Commons status inspection must be assigned to the Safety Steward."
            )

    def _prompt(
        self,
        *,
        message: str,
        vault_id: VaultId,
        error_feedback: str,
    ) -> str:
        """Builds a few-shot completion prompt for the pretrained base model."""

        roster = "\n".join(
            f"- {planet.id}: circles={','.join(planet.circle_ids)}; "
            f"{planet.display_name}; {planet.charter.purpose}"
            for planet in sorted(self.registry.planets.values(), key=lambda item: item.id)
            if planet.status not in {
                LifecycleStatus.QUARANTINED,
                LifecycleStatus.RETIRED,
            }
        )
        correction = (
            f"\nThe previous plan was invalid: {error_feedback}. Correct it.\n"
            if error_feedback
            else ""
        )
        return f"""Natural-language requests are converted to one JSON action plan.
The language model must choose the Planet and actions. Do not use keyword rules.
Current UTC time: {datetime.now(UTC).isoformat()}
Selected Vault: {vault_id}

Allowed actions and exact argument keys:
- respond: {{}}
- calculate: {{"expression":"12*(3+4)"}}
- unit_convert: {{"value":5,"from_unit":"miles","to_unit":"km"}}
- memory_write: {{"content":"fact","tags":["optional"]}}
- memory_search: {{"query":"topic","limit":5}}
- artifact_create: {{"name":"title","kind":"document","content":"text"}}; artifact_id is optional for a new version
- artifact_list: {{}}
- knowledge_add: {{"title":"source title","content":"source text"}}; source_uri and tags are optional
- knowledge_search or knowledge_summarize: {{"query":"topic","limit":5}}
- knowledge_verify: {{"claims":["claim"]}}; source_ids is optional
- review_create: {{"title":"review title","due_at":"timezone-aware ISO timestamp"}}; recurrence_days and payload are optional
- review_list: {{}}; status is optional
- calendar_propose: {{"title":"event","starts_at":"timezone-aware ISO timestamp","ends_at":"timezone-aware ISO timestamp","details":"optional"}}
- calendar_list: {{"include_proposed":true}}
- approval_list: {{"status":"pending"}}
- approval_decide: {{"approval_id":"approval-...","decision":"approved|rejected|cancelled","decided_by":"local_user"}}
- commons_status: {{}}

Safety rules:
- There is no action for sending email, calling, buying, paying, or changing an external provider. Use respond for advisory help with those requests.
- Choose respond for ordinary questions, planning, brainstorming, research reasoning, scientific exploration, or startup advice that does not request one of the explicit local actions.
- Use more than one action only when the user explicitly requests multiple local operations.
- Preserve user-supplied facts; do not invent arguments or identifiers.
- Select circle_id and planet_id semantically from the roster; the Planet must belong to the Circle.
- Choose a Planet whose Charter authorizes every action; for memory actions it must also authorize the selected Vault.

Planet roster:
{roster}

Examples:
Request: Please keep in mind that Mom likes calls on Sundays.
Plan: {{"circle_id":"commons","planet_id":"personal_steward","actions":[{{"action":"memory_write","arguments":{{"content":"Mom likes calls on Sundays"}},"reason":"The user explicitly asked to retain a personal preference."}}],"reasoning_summary":"Store the supplied preference in the selected Vault."}}

Request: Can you remember my mother prefers a phone call Sunday evening?
Plan: {{"circle_id":"commons","planet_id":"personal_steward","actions":[{{"action":"memory_write","arguments":{{"content":"My mother prefers a phone call Sunday evening"}},"reason":"The user asked to remember a supplied fact."}}],"reasoning_summary":"Write the fact to personal memory."}}

Request: What have I told you concerning groceries?
Plan: {{"circle_id":"commons","planet_id":"personal_steward","actions":[{{"action":"memory_search","arguments":{{"query":"groceries","limit":5}},"reason":"The user asked to recall stored information."}}],"reasoning_summary":"Search the selected Vault."}}

Request: Work out twelve times seven.
Plan: {{"circle_id":"commons","planet_id":"personal_steward","actions":[{{"action":"calculate","arguments":{{"expression":"12*7"}},"reason":"The user requested exact arithmetic."}}],"reasoning_summary":"Use the authorized Calculate Satellite."}}

Request: Please create a memo called Battery thesis containing Sodium ion may cut material cost.
Plan: {{"circle_id":"life_admin","planet_id":"digital_librarian","actions":[{{"action":"artifact_create","arguments":{{"name":"Battery thesis","kind":"memo","content":"Sodium ion may cut material cost."}},"reason":"The user asked to create a versioned memo."}}],"reasoning_summary":"Create a local artifact version."}}

Request: Search my evidence sources for sodium batteries.
Plan: {{"circle_id":"science_lab","planet_id":"knowledge_librarian","actions":[{{"action":"knowledge_search","arguments":{{"query":"sodium batteries","limit":10}},"reason":"The user asked to search ingested evidence."}}],"reasoning_summary":"Search local Knowledge Sources with citations."}}

Request: Schedule a review titled Check satcom idea for 2026-10-03T09:00:00+05:30 and remember the idea uses optical links.
Plan: {{"circle_id":"commons","planet_id":"safety_steward","actions":[{{"action":"memory_write","arguments":{{"content":"The satcom idea uses optical links"}},"reason":"Retain the explicit idea."}},{{"action":"review_create","arguments":{{"title":"Check satcom idea","due_at":"2026-10-03T09:00:00+05:30"}},"reason":"Schedule the explicitly requested review."}}],"reasoning_summary":"Store the idea and schedule its review."}}

Request: Put a one-hour call with Mom on my local calendar on 2026-10-03 at 18:00 India time.
Plan: {{"circle_id":"life_admin","planet_id":"schedule_coordinator","actions":[{{"action":"calendar_propose","arguments":{{"title":"Call Mom","starts_at":"2026-10-03T18:00:00+05:30","ends_at":"2026-10-03T19:00:00+05:30","details":"Local proposal only"}},"reason":"The user requested a local calendar proposal."}}],"reasoning_summary":"Create a local proposal without provider I/O."}}

Request: Help me compare energy-storage startup opportunities.
Plan: {{"circle_id":"venture_exploration","planet_id":"opportunity_portfolio_steward","actions":[{{"action":"respond","arguments":{{}},"reason":"The user requested open-ended advisory reasoning."}}],"reasoning_summary":"Route advisory work to the opportunity portfolio specialist."}}
{correction}
Request: {message}
Plan:"""

    @staticmethod
    def _bounded_error(exc: Exception) -> str:
        """Returns a short schema/authority diagnostic for a model retry."""

        if isinstance(exc, ValidationError):
            parts = [
                f"{'.'.join(str(item) for item in error['loc'])}: {error['msg']}"
                for error in exc.errors()[:5]
            ]
            return "; ".join(parts)[:1_000]
        return f"{type(exc).__name__}: {exc}"[:1_000]

    def _record(
        self,
        event_type: str,
        summary: str,
        status: str,
        *,
        mission_id: str,
        severity: Severity = Severity.INFO,
        duration_ms: float | None = None,
        attributes: dict[str, Any],
    ) -> None:
        """Emits content-free planner telemetry without affecting Chat."""

        if self.event_recorder is None:
            return
        try:
            self.event_recorder.record(
                event_type,
                summary=summary,
                status=status,
                severity=severity,
                mission_id=mission_id,
                actor=EntityReference(kind="service", id="natural_language_planner"),
                subject=EntityReference(kind="rogue_star", id="mac_gemma"),
                duration_ms=duration_ms,
                attributes=attributes,
            )
        except Exception:
            return


class NaturalLanguageActionExecutor:
    """Executes only validated actions selected by the model planner."""

    def __init__(
        self,
        *,
        commons: CommonsRuntime,
        satellites: LocalSatelliteRuntime,
    ) -> None:
        """Composes reusable Commons services and authorized Satellites."""

        self.commons = commons
        self.satellites = satellites

    def execute(
        self,
        action: NaturalLanguageAction,
        *,
        planet_id: str,
        mission_id: str,
        vault_id: VaultId,
    ) -> ActionInvocation | None:
        """Executes one validated local action; advisory `respond` has no effect."""

        if action.action == "respond":
            return None
        output = self._execute(
            action,
            planet_id=planet_id,
            mission_id=mission_id,
            vault_id=vault_id,
        )
        return ActionInvocation(
            action=action.action,
            planet_id=planet_id,
            arguments=action.arguments,
            output=output,
            reason=action.reason,
        )

    def _execute(
        self,
        action: NaturalLanguageAction,
        *,
        planet_id: str,
        mission_id: str,
        vault_id: VaultId,
    ) -> dict[str, Any]:
        """Dispatches a schema-validated action to its concrete local service."""

        name = action.action
        args = action.arguments
        if name in {"calculate", "unit_convert", "memory_write", "memory_search"}:
            call = self._satellite_call(
                action,
                vault_id=vault_id,
                source_id=mission_id,
            )
            result = self.satellites.invoke(
                call,
                planet_id=planet_id,
                mission_id=mission_id,
            )
            return dict(result.get("output", {}))
        if name == "artifact_create":
            artifact = self.commons.create_artifact(
                ArtifactCreate.model_validate(args)
            )
            return artifact.model_dump(mode="json")
        if name == "artifact_list":
            return {
                "artifacts": [
                    item.model_dump(mode="json")
                    for item in self.commons.list_artifacts()
                ]
            }
        if name == "knowledge_add":
            source = self.commons.add_knowledge_source(
                KnowledgeSourceCreate.model_validate(args)
            )
            return source.model_dump(mode="json")
        if name == "knowledge_search":
            hits = self.commons.search_knowledge(
                args["query"],
                limit=args.get("limit", 10),
            )
            return {"hits": [item.model_dump(mode="json") for item in hits]}
        if name == "knowledge_summarize":
            summary = self.commons.summarize_knowledge(
                args["query"],
                limit=args.get("limit", 5),
            )
            return summary.model_dump(mode="json")
        if name == "knowledge_verify":
            assessments = self.commons.verify_claims(
                ClaimVerificationRequest.model_validate(args)
            )
            return {
                "assessments": [
                    item.model_dump(mode="json") for item in assessments
                ]
            }
        if name == "review_create":
            review = self.commons.create_review(
                ScheduledReviewCreate.model_validate(args)
            )
            return review.model_dump(mode="json")
        if name == "review_list":
            reviews = self.commons.list_reviews(status=args.get("status"))
            return {
                "reviews": [item.model_dump(mode="json") for item in reviews]
            }
        if name == "calendar_propose":
            proposal = self.commons.propose_calendar(
                CalendarProposalCreate.model_validate(args)
            )
            return proposal.model_dump(mode="json")
        if name == "calendar_list":
            items = self.commons.inspect_calendar(
                include_proposed=args.get("include_proposed", True)
            )
            return {"items": [item.model_dump(mode="json") for item in items]}
        if name == "approval_list":
            approvals = self.commons.list_approvals(status=args.get("status"))
            return {
                "approvals": [
                    item.model_dump(mode="json") for item in approvals
                ]
            }
        if name == "approval_decide":
            decision = ApprovalDecision.model_validate(
                {key: value for key, value in args.items() if key != "approval_id"}
            )
            approval = self.commons.decide_approval(
                args["approval_id"],
                decision,
            )
            return approval.model_dump(mode="json")
        if name == "commons_status":
            return {
                "backend": self.commons.backend,
                "counts": self.commons.counts(),
                "capabilities": sorted(self.commons.capabilities()),
                "external_effects": False,
            }
        raise ValueError(f"Unsupported planned action: {name}")

    @staticmethod
    def _satellite_call(
        action: NaturalLanguageAction, *, vault_id: VaultId, source_id: str
    ) -> PlannedSatelliteCall:
        """Adapts model actions to the canonical local Satellite contract."""

        name = action.action
        if name == "memory_write":
            content = str(action.arguments["content"])
            arguments = {
                "item": {
                    "type": "semantic",
                    "layer": "warm",
                    "scope": "agent_local",
                    "agent_id": f"galaxy_chat:{vault_id}",
                    "content": {"fact": content},
                    "content_text": content,
                    "source_type": "user",
                    "source_id": source_id,
                    "tags": [*action.arguments.get("tags", []), "wormhole_chat"],
                    "metadata": {"vault_id": vault_id},
                    "confidence": 1.0,
                }
            }
        elif name == "memory_search":
            arguments = {
                "query": action.arguments["query"],
                "filters": {"vault_id": vault_id},
                "limit": action.arguments.get("limit", 5),
            }
        else:
            arguments = dict(action.arguments)
        return PlannedSatelliteCall(
            satellite_id=name,
            vault_id=(vault_id if name.startswith("memory_") else None),
            arguments=arguments,
            reason=action.reason,
        )


__all__ = [
    "ActionInvocation",
    "ActionName",
    "NaturalLanguageAction",
    "NaturalLanguageActionExecutor",
    "NaturalLanguagePlan",
    "NaturalLanguagePlanner",
    "NaturalLanguagePlanningError",
    "PlannedChatTurn",
    "PlanningEvidence",
    "SUPPORTED_ACTIONS",
]
