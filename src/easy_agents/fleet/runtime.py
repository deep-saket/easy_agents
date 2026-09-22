"""Reusable runtime that turns every Charter into a bounded Specialist."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from easy_agents.fleet.models import (
    AgentResult,
    ApprovalRequest,
    FleetMissionResult,
    MissionRequest,
    MissionStatus,
    PermissionGrant,
    PlaybookSpec,
    RouteCandidate,
    SpecialistManifest,
    SpecialistStatus,
    StepKind,
    StepResult,
    WorkOrder,
)
from easy_agents.fleet.policy import PolicyDecision, PolicyEngine, infer_effects
from easy_agents.fleet.registry import FleetRegistry


class SpecialistAgent:
    """One manifest-backed agent using shared Playbooks and policy enforcement."""

    def __init__(
        self,
        *,
        manifest: SpecialistManifest,
        registry: FleetRegistry,
        llm: Any | None = None,
        policy_engine: PolicyEngine | None = None,
    ) -> None:
        self.manifest = manifest
        self.registry = registry
        self.llm = llm
        self.policy_engine = policy_engine or PolicyEngine(registry)

    def run(
        self,
        request: MissionRequest,
        *,
        mission_id: str | None = None,
        parent_order_id: str | None = None,
        parent_permissions: PermissionGrant | None = None,
    ) -> AgentResult:
        """Runs a safe advisory turn or pauses at a policy Gate."""

        active_mission_id = mission_id or f"mission-{uuid4()}"
        run_id = f"run-{uuid4()}"
        playbook = self._select_playbook(request)
        effects = sorted(set(request.requested_effects) | infer_effects(request.objective))
        requested_scope = request.memory_scope or self._default_scope()
        permissions = PermissionGrant(
            effects=effects,
            memory_scopes=[requested_scope],
            allow_network=request.allow_network,
        )
        if parent_permissions is not None:
            permissions = parent_permissions.narrowed_for(self.manifest)
        order = WorkOrder(
            id=f"work-{uuid4()}",
            mission_id=active_mission_id,
            parent_order_id=parent_order_id,
            specialist_id=self.manifest.id,
            objective=request.objective,
            playbook_id=playbook.id,
            permissions=permissions,
        )

        lifecycle_block = self._lifecycle_block()
        if lifecycle_block:
            return self._blocked_result(
                run_id=run_id,
                mission_id=active_mission_id,
                playbook=playbook,
                order=order,
                reasons=[lifecycle_block],
            )

        decision = self.policy_engine.evaluate(
            manifest=self.manifest,
            request=request,
            playbook=playbook,
            parent_permissions=parent_permissions,
        )
        if decision.outcome == "block":
            return self._blocked_result(
                run_id=run_id,
                mission_id=active_mission_id,
                playbook=playbook,
                order=order,
                reasons=decision.reasons,
            )
        if decision.outcome == "approval":
            approval = ApprovalRequest(
                id=f"approval-{uuid4()}",
                mission_id=active_mission_id,
                specialist_id=self.manifest.id,
                effects=decision.approval_effects,
                rationale=" ".join(decision.reasons),
            )
            return AgentResult(
                run_id=run_id,
                mission_id=active_mission_id,
                specialist_id=self.manifest.id,
                specialist_name=self.manifest.display_name,
                status=MissionStatus.AWAITING_APPROVAL,
                playbook_id=playbook.id,
                response=(
                    f"{self.manifest.display_name} prepared the {playbook.display_name} "
                    "Playbook but stopped before the requested external effect."
                ),
                steps=self._step_results(playbook, decision, waiting=True),
                warnings=decision.reasons,
                approvals=[approval],
                work_order=order,
            )

        warnings = list(decision.reasons)
        if self.manifest.status == SpecialistStatus.SANDBOXED:
            warnings.append(
                "This Specialist is sandboxed: it may reason and draft, but it has not been evaluated or activated for autonomous effects."
            )
        try:
            response, model_id = self._generate_response(
                request=request,
                playbook=playbook,
                decision=decision,
            )
        except Exception as exc:
            return AgentResult(
                run_id=run_id,
                mission_id=active_mission_id,
                specialist_id=self.manifest.id,
                specialist_name=self.manifest.display_name,
                status=MissionStatus.FAILED,
                playbook_id=playbook.id,
                response=f"Local model execution failed for {self.manifest.display_name}.",
                steps=self._step_results(playbook, decision, blocked=True),
                warnings=[*warnings, f"Model error: {type(exc).__name__}: {exc}"],
                work_order=order,
            )

        status = MissionStatus.COMPLETED if self.llm is not None else MissionStatus.PLANNED
        return AgentResult(
            run_id=run_id,
            mission_id=active_mission_id,
            specialist_id=self.manifest.id,
            specialist_name=self.manifest.display_name,
            status=status,
            playbook_id=playbook.id,
            response=response,
            steps=self._step_results(playbook, decision, completed=self.llm is not None),
            warnings=warnings,
            used_model=model_id,
            work_order=order,
        )

    def _select_playbook(self, request: MissionRequest) -> PlaybookSpec:
        if request.preferred_playbook_id:
            preferred = request.preferred_playbook_id.removeprefix("playbook:")
            if preferred not in self.manifest.playbook_ids:
                raise ValueError(
                    f"Specialist {self.manifest.id!r} does not declare Playbook {preferred!r}."
                )
            return self.registry.get_playbook(preferred)
        objective_terms = set(request.objective.lower().replace("-", " ").split())
        best: tuple[float, PlaybookSpec] | None = None
        for playbook_id in self.manifest.playbook_ids:
            playbook = self.registry.get_playbook(playbook_id)
            haystack = " ".join(
                [playbook.display_name, playbook.description, *playbook.tags]
            ).lower()
            score = sum(term in haystack for term in objective_terms)
            candidate = (float(score), playbook)
            if best is None or candidate[0] > best[0]:
                best = candidate
        assert best is not None
        return best[1]

    def _generate_response(
        self,
        *,
        request: MissionRequest,
        playbook: PlaybookSpec,
        decision: PolicyDecision,
    ) -> tuple[str, str | None]:
        if self.llm is None:
            step_lines = "\n".join(
                f"{index}. {step.title}: {step.instruction}"
                for index, step in enumerate(playbook.steps, start=1)
            )
            return (
                f"{self.manifest.display_name} is ready to handle: {request.objective}\n\n"
                f"Playbook: {playbook.display_name}\n"
                f"Memory scope: {decision.memory_scope}\n"
                f"Execution plan:\n{step_lines}\n\n"
                "No model was called. Configure the local Mac Gemma profile to produce the specialist's advisory result.",
                None,
            )

        system_prompt = self._system_prompt(playbook=playbook, decision=decision)
        user_prompt = (
            f"Mission: {request.objective}\n"
            f"Context: {request.context}\n"
            "Return a concise advisory result. Separate facts, assumptions, uncertainties, "
            "and next actions. Never claim an external action was performed."
        )
        response = self.llm.generate(system_prompt, user_prompt)
        model_id = getattr(self.llm, "model_name", type(self.llm).__name__)
        return str(response).strip(), str(model_id)

    def _system_prompt(self, *, playbook: PlaybookSpec, decision: PolicyDecision) -> str:
        steps = "\n".join(
            f"- {step.title}: {step.instruction}" for step in playbook.steps
        )
        return (
            f"You are {self.manifest.display_name}, one narrow Specialist in a private local-first agent Constellation.\n"
            f"Charter: {self.manifest.purpose}\n"
            f"Guilds: {', '.join(self.manifest.guilds)}\n"
            f"Memory scope: {decision.memory_scope}. Do not imply access to data that was not provided.\n"
            f"Policies: {', '.join(self.manifest.policy_ids)}.\n"
            f"Playbook: {playbook.display_name}\n{steps}\n"
            "Stay within the Charter. Do not diagnose, prescribe, provide legal authority, reveal chain-of-thought, "
            "or perform/send/purchase/publish anything. Label unsupported statements as hypotheses."
        )

    def _step_results(
        self,
        playbook: PlaybookSpec,
        decision: PolicyDecision,
        *,
        completed: bool = False,
        waiting: bool = False,
        blocked: bool = False,
    ) -> list[StepResult]:
        results: list[StepResult] = []
        for step in playbook.steps:
            if blocked:
                status = "blocked"
            elif waiting and (
                step.kind == StepKind.GATE
                or set(step.effects) & set(decision.approval_effects)
            ):
                status = "waiting"
            elif waiting:
                status = "planned"
            elif completed and step.kind not in {StepKind.TOOL, StepKind.GATE}:
                status = "completed"
            else:
                status = "planned"
            results.append(
                StepResult(
                    step_id=step.id,
                    title=step.title,
                    kind=step.kind,
                    status=status,
                    summary=step.instruction,
                    effects=step.effects,
                )
            )
        return results

    def _blocked_result(
        self,
        *,
        run_id: str,
        mission_id: str,
        playbook: PlaybookSpec,
        order: WorkOrder,
        reasons: list[str],
    ) -> AgentResult:
        decision = PolicyDecision(
            outcome="block",
            effective_effects=order.permissions.effects,
            memory_scope=order.permissions.memory_scopes[0]
            if order.permissions.memory_scopes
            else "none",
            reasons=reasons,
            policy_ids=self.manifest.policy_ids,
        )
        return AgentResult(
            run_id=run_id,
            mission_id=mission_id,
            specialist_id=self.manifest.id,
            specialist_name=self.manifest.display_name,
            status=MissionStatus.BLOCKED,
            playbook_id=playbook.id,
            response=f"{self.manifest.display_name} did not run because policy blocked the Mission.",
            steps=self._step_results(playbook, decision, blocked=True),
            warnings=reasons,
            work_order=order,
        )

    def _lifecycle_block(self) -> str | None:
        if self.manifest.status == SpecialistStatus.QUARANTINED:
            return "The Specialist is quarantined and cannot accept new Missions."
        if self.manifest.status == SpecialistStatus.RETIRED:
            return "The Specialist is retired and cannot accept new Missions."
        return None

    def _default_scope(self) -> str:
        for preferred in ("employer_authorized", "personal", "exploration", "long_term", "working"):
            if preferred in self.manifest.memory_scope_ids:
                return preferred
        return self.manifest.memory_scope_ids[0]


class FleetRuntime:
    """Routes Missions and coordinates bounded Specialist Work orders."""

    def __init__(
        self,
        *,
        registry: FleetRegistry | None = None,
        llm: Any | None = None,
    ) -> None:
        self.registry = registry or FleetRegistry.default()
        self.llm = llm
        self.policy_engine = PolicyEngine(self.registry)

    def agent(self, specialist_id: str) -> SpecialistAgent:
        """Instantiates one lightweight agent; no process is kept alive per Charter."""

        return SpecialistAgent(
            manifest=self.registry.get_specialist(specialist_id),
            registry=self.registry,
            llm=self.llm,
            policy_engine=self.policy_engine,
        )

    def route(self, request: MissionRequest) -> list[RouteCandidate]:
        """Returns the selected team in execution order."""

        if request.specialist_id:
            manifest = self.registry.get_specialist(request.specialist_id)
            explicit = RouteCandidate(
                specialist_id=manifest.id,
                display_name=manifest.display_name,
                score=1.0,
                matched_terms=["explicit-selection"],
                status=manifest.status,
                guilds=manifest.guilds,
            )
            if request.team_size == 1:
                return [explicit]
            additional = [
                item
                for item in self.registry.route(request.objective, limit=request.team_size + 1)
                if item.specialist_id != manifest.id
            ]
            return [explicit, *additional[: request.team_size - 1]]
        return self.registry.route(request.objective, limit=request.team_size)

    def run(self, request: MissionRequest) -> FleetMissionResult:
        """Executes one safe local Mission across the routed team."""

        mission_id = f"mission-{uuid4()}"
        candidates = self.route(request)
        results: list[AgentResult] = []
        for candidate in candidates:
            manifest = self.registry.get_specialist(candidate.specialist_id)
            requested_scope = request.memory_scope or _preferred_scope(manifest)
            permissions = PermissionGrant(
                effects=sorted(set(request.requested_effects) | infer_effects(request.objective)),
                memory_scopes=[requested_scope],
                allow_network=request.allow_network,
            )
            specialist_request = request.model_copy(
                update={
                    "specialist_id": manifest.id,
                    "memory_scope": requested_scope,
                    "team_size": 1,
                }
            )
            results.append(
                self.agent(manifest.id).run(
                    specialist_request,
                    mission_id=mission_id,
                    parent_permissions=permissions,
                )
            )
        status = _aggregate_status(results)
        warnings = [warning for result in results for warning in result.warnings]
        return FleetMissionResult(
            mission_id=mission_id,
            objective=request.objective,
            status=status,
            routed_specialists=candidates,
            results=results,
            synthesis=_synthesize(results),
            warnings=list(dict.fromkeys(warnings)),
        )


def _preferred_scope(manifest: SpecialistManifest) -> str:
    for preferred in ("employer_authorized", "personal", "exploration", "long_term", "working"):
        if preferred in manifest.memory_scope_ids:
            return preferred
    return manifest.memory_scope_ids[0]


def _aggregate_status(results: list[AgentResult]) -> MissionStatus:
    statuses = {item.status for item in results}
    for status in (
        MissionStatus.FAILED,
        MissionStatus.BLOCKED,
        MissionStatus.AWAITING_APPROVAL,
        MissionStatus.PLANNED,
        MissionStatus.COMPLETED,
    ):
        if status in statuses:
            return status
    return MissionStatus.FAILED


def _synthesize(results: list[AgentResult]) -> str:
    if not results:
        return "No Specialist accepted the Mission."
    if len(results) == 1:
        return results[0].response
    sections = [
        f"{item.specialist_name} [{item.status.value}]:\n{item.response}"
        for item in results
    ]
    return "\n\n".join(sections)
