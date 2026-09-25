"""Reusable runtime that turns every Charter into a bounded Specialist."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Mapping
from uuid import uuid4

from easy_agents.fleet.models import (
    AgentResult,
    ApprovalRequest,
    GalaxyRoutePlan,
    FleetMissionResult,
    FleetValidationItem,
    FleetValidationReport,
    GenerationEvidence,
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
from easy_agents.fleet.gateway import WormholeRouter
from easy_agents.fleet.policy import PolicyDecision, PolicyEngine, infer_effects
from easy_agents.fleet.registry import FleetRegistry
from easy_agents.observability import EntityReference, Severity


_DEFAULT_MODEL = object()


class SpecialistAgent:
    """One manifest-backed agent using shared Playbooks and policy enforcement."""

    def __init__(
        self,
        *,
        manifest: SpecialistManifest,
        registry: FleetRegistry,
        llm: Any | None = None,
        policy_engine: PolicyEngine | None = None,
        event_recorder: Any | None = None,
    ) -> None:
        self.manifest = manifest
        self.registry = registry
        self.llm = llm
        self.policy_engine = policy_engine or PolicyEngine(registry)
        self.event_recorder = event_recorder

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
        started = perf_counter()
        playbook = self._select_playbook(request)
        inferred_effects = set() if request.advisory_only else infer_effects(request.objective)
        effects = sorted(set(request.requested_effects) | inferred_effects)
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
        self._record(
            "work_order.created",
            summary=f"Work order created for {self.manifest.display_name}",
            status="queued",
            mission_id=active_mission_id,
            work_order_id=order.id,
            run_id=run_id,
            subject=EntityReference(kind="playbook", id=playbook.id),
            attributes={
                "specialist_id": self.manifest.id,
                "playbook_id": playbook.id,
                "memory_scope": requested_scope,
                "effects": effects,
            },
        )
        self._record(
            "specialist.selected",
            summary=f"Selected {self.manifest.display_name}",
            status="selected",
            mission_id=active_mission_id,
            work_order_id=order.id,
            run_id=run_id,
            attributes={
                "specialist_id": self.manifest.id,
                "playbook_id": playbook.id,
                "guilds": self.manifest.guilds,
                "source_status": self.manifest.status.value,
            },
        )
        self._record(
            "specialist.started",
            summary=f"{self.manifest.display_name} started",
            status="running",
            mission_id=active_mission_id,
            work_order_id=order.id,
            run_id=run_id,
            subject=EntityReference(kind="playbook", id=playbook.id),
            attributes={
                "specialist_id": self.manifest.id,
                "playbook_id": playbook.id,
            },
        )
        self._record(
            "playbook.started",
            summary=f"{playbook.display_name} started",
            status="running",
            mission_id=active_mission_id,
            work_order_id=order.id,
            run_id=run_id,
            subject=EntityReference(kind="playbook", id=playbook.id),
            attributes={"playbook_id": playbook.id},
        )

        lifecycle_block = self._lifecycle_block()
        if lifecycle_block:
            self._record(
                "policy.blocked",
                summary=f"Lifecycle policy blocked {self.manifest.display_name}",
                status="blocked",
                severity=Severity.WARNING,
                mission_id=active_mission_id,
                work_order_id=order.id,
                run_id=run_id,
                subject=EntityReference(kind="policy", id="lifecycle"),
                attributes={"reason_count": 1},
            )
            result = self._blocked_result(
                run_id=run_id,
                mission_id=active_mission_id,
                playbook=playbook,
                order=order,
                reasons=[lifecycle_block],
            )
            self._record_result(result, playbook=playbook, started=started)
            return result

        decision = self.policy_engine.evaluate(
            manifest=self.manifest,
            request=request,
            playbook=playbook,
            parent_permissions=parent_permissions,
        )
        if decision.outcome == "block":
            self._record(
                "policy.blocked",
                summary=f"Policy blocked {self.manifest.display_name}",
                status="blocked",
                severity=Severity.WARNING,
                mission_id=active_mission_id,
                work_order_id=order.id,
                run_id=run_id,
                subject=self._policy_subject(),
                attributes={
                    "policy_ids": decision.policy_ids,
                    "reason_count": len(decision.reasons),
                    "effects": decision.effective_effects,
                },
            )
            result = self._blocked_result(
                run_id=run_id,
                mission_id=active_mission_id,
                playbook=playbook,
                order=order,
                reasons=decision.reasons,
            )
            self._record_result(result, playbook=playbook, started=started)
            return result
        if decision.outcome == "approval":
            approval = ApprovalRequest(
                id=f"approval-{uuid4()}",
                mission_id=active_mission_id,
                specialist_id=self.manifest.id,
                effects=decision.approval_effects,
                rationale=" ".join(decision.reasons),
            )
            self._record(
                "approval.requested",
                summary=f"Approval required for {self.manifest.display_name}",
                status="awaiting_approval",
                severity=Severity.WARNING,
                mission_id=active_mission_id,
                work_order_id=order.id,
                run_id=run_id,
                subject=EntityReference(kind="approval", id=approval.id),
                attributes={
                    "approval_id": approval.id,
                    "effects": decision.approval_effects,
                    "policy_ids": decision.policy_ids,
                },
            )
            result = AgentResult(
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
            self._record_result(result, playbook=playbook, started=started)
            return result

        self._record(
            "policy.allowed",
            summary=f"Policy allowed {self.manifest.display_name}",
            status="allowed",
            mission_id=active_mission_id,
            work_order_id=order.id,
            run_id=run_id,
            subject=self._policy_subject(),
            attributes={
                "policy_ids": decision.policy_ids,
                "effects": decision.effective_effects,
                "memory_scope": decision.memory_scope,
            },
        )

        warnings = list(decision.reasons)
        if self.manifest.status == SpecialistStatus.SANDBOXED:
            warnings.append(
                "This Specialist is sandboxed: it may reason and draft, but it has not been evaluated or activated for autonomous effects."
            )
        if self.llm is not None:
            warnings.append(
                "Model-generated content is unverified; check claims, measurements, and recommendations before relying on it."
            )
        try:
            response, model_id, generation = self._generate_response(
                request=request,
                playbook=playbook,
                decision=decision,
                mission_id=active_mission_id,
                work_order_id=order.id,
                run_id=run_id,
            )
        except Exception as exc:
            failed_generation_id = str(
                getattr(exc, "generation_id", f"generation-{uuid4()}")
            )
            result = AgentResult(
                run_id=run_id,
                mission_id=active_mission_id,
                specialist_id=self.manifest.id,
                specialist_name=self.manifest.display_name,
                status=MissionStatus.FAILED,
                playbook_id=playbook.id,
                response=f"Local model execution failed for {self.manifest.display_name}.",
                steps=self._step_results(playbook, decision, blocked=True),
                warnings=[*warnings, f"Model error: {type(exc).__name__}: {exc}"],
                used_model=str(getattr(self.llm, "model_name", type(self.llm).__name__)),
                generation=GenerationEvidence(
                    generation_id=failed_generation_id,
                    model_id=str(
                        getattr(self.llm, "model_name", type(self.llm).__name__)
                    ),
                    completed=False,
                    output_used=False,
                    duration_ms=getattr(exc, "generation_duration_ms", None),
                    quality_status="rejected",
                    quality_checks=["generation_failed"],
                ),
                work_order=order,
            )
            self._record_result(result, playbook=playbook, started=started)
            return result

        if generation is not None and generation.quality_status != "accepted":
            disposition = (
                " Its output was not used."
                if generation.quality_status == "rejected"
                else ""
            )
            warnings.append(
                "Model completion passed transport checks but failed basic output checks: "
                + ", ".join(generation.quality_checks)
                + "."
                + disposition
            )
        used_generated_output = generation is not None and generation.output_used
        status = (
            MissionStatus.COMPLETED
            if used_generated_output
            else MissionStatus.PLANNED
        )
        result = AgentResult(
            run_id=run_id,
            mission_id=active_mission_id,
            specialist_id=self.manifest.id,
            specialist_name=self.manifest.display_name,
            status=status,
            playbook_id=playbook.id,
            response=response,
            steps=self._step_results(
                playbook,
                decision,
                completed=used_generated_output,
            ),
            warnings=warnings,
            used_model=model_id,
            generation=generation,
            work_order=order,
        )
        self._record_result(result, playbook=playbook, started=started)
        return result

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
        mission_id: str,
        work_order_id: str,
        run_id: str,
    ) -> tuple[str, str | None, GenerationEvidence | None]:
        if self.llm is None:
            return (
                self._planned_response(
                    request=request,
                    playbook=playbook,
                    decision=decision,
                    note=(
                        "No model was called. Configure the local Mac Gemma profile "
                        "to produce the specialist's advisory result."
                    ),
                ),
                None,
                None,
            )

        model_id = getattr(self.llm, "model_name", type(self.llm).__name__)
        is_mac_gemma = "gemma" in str(model_id).lower()
        system_prompt = self._system_prompt(playbook=playbook, decision=decision)
        user_prompt = (
            f"Mission: {request.objective}\n"
            f"Context: {request.context}\n"
            "Return a concise advisory result. Separate supplied facts from assumptions, "
            "state uncertainty, and finish with one reversible next action. Do not invent "
            "measurements or claim an external action was performed."
        )
        response_prefix = ""
        if is_mac_gemma:
            # The external service hosts a pretrained completion model, not an
            # instruction-tuned chat model. A short document continuation is
            # materially more reliable than feeding it the framework's full
            # charter and asking it to follow instructions. Policy and effect
            # enforcement have already happened deterministically above.
            response_prefix = (
                f'{self.manifest.display_name} assessment of the Mission '
                f'"{request.objective}": '
            )
            system_prompt = ""
            user_prompt = (
                f"Supplied context: {request.context}.\n\n{response_prefix}"
                if request.context
                else response_prefix
            )
        model_entity_id = "mac_gemma" if is_mac_gemma else str(model_id)
        span_id = f"span-{uuid4()}"
        generation_id = f"generation-{uuid4()}"
        self._record(
            "model.started",
            summary=f"Model {model_id} started",
            status="running",
            mission_id=mission_id,
            work_order_id=work_order_id,
            run_id=run_id,
            span_id=span_id,
            subject=EntityReference(kind="model", id=model_entity_id),
            attributes={
                "model_id": str(model_id),
                "call_kind": "generate",
                "generation_id": generation_id,
            },
        )
        model_started = perf_counter()
        try:
            generate_result = getattr(self.llm, "generate_result", None)
            if callable(generate_result):
                raw_generation = generate_result(system_prompt, user_prompt)
                response_text = str(getattr(raw_generation, "content", "")).strip()
                finish_reason = _optional_text(
                    getattr(raw_generation, "finish_reason", None)
                )
                prompt_tokens = _optional_nonnegative_int(
                    getattr(raw_generation, "prompt_tokens", None)
                )
                completion_tokens = _optional_nonnegative_int(
                    getattr(raw_generation, "completion_tokens", None)
                )
                total_tokens = _optional_nonnegative_int(
                    getattr(raw_generation, "total_tokens", None)
                )
            else:
                response = self.llm.generate(system_prompt, user_prompt)
                response_text = str(response).strip()
                finish_reason = None
                prompt_tokens = None
                completion_tokens = None
                total_tokens = None
            if not response_text:
                raise ValueError(f"Model {model_id} returned an empty completion.")
        except Exception as exc:
            failure_duration_ms = round((perf_counter() - model_started) * 1000, 3)
            self._record(
                "model.failed",
                summary=f"Model {model_id} failed",
                status="failed",
                severity=Severity.ERROR,
                mission_id=mission_id,
                work_order_id=work_order_id,
                run_id=run_id,
                span_id=span_id,
                subject=EntityReference(kind="model", id=model_entity_id),
                duration_ms=failure_duration_ms,
                attributes={
                    "model_id": str(model_id),
                    "call_kind": "generate",
                    "error_type": type(exc).__name__,
                    "generation_id": generation_id,
                },
            )
            try:
                setattr(exc, "generation_id", generation_id)
                setattr(exc, "generation_duration_ms", failure_duration_ms)
            except Exception:
                pass
            raise
        duration_ms = round((perf_counter() - model_started) * 1000, 3)
        quality_status, quality_checks = _assess_generation_quality(
            response_text,
            finish_reason=finish_reason,
            response_prefix=response_prefix,
            objective=request.objective,
        )
        output_used = quality_status != "rejected"
        metrics = {
            key: value
            for key, value in {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            }.items()
            if value is not None
        }
        self._record(
            "model.completed",
            summary=f"Model {model_id} completed",
            status="completed",
            mission_id=mission_id,
            work_order_id=work_order_id,
            run_id=run_id,
            span_id=span_id,
            subject=EntityReference(kind="model", id=model_entity_id),
            duration_ms=duration_ms,
            attributes={
                "model_id": str(model_id),
                "call_kind": "generate",
                "generation_id": generation_id,
                "finish_reason": finish_reason,
                "quality_status": quality_status,
                "quality_checks": quality_checks,
                "output_used": output_used,
            },
            metrics=metrics,
        )
        evidence = GenerationEvidence(
            generation_id=generation_id,
            model_id=str(model_id),
            completed=True,
            output_used=output_used,
            finish_reason=finish_reason,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            quality_status=quality_status,
            quality_checks=quality_checks,
        )
        if not output_used:
            return (
                self._planned_response(
                    request=request,
                    playbook=playbook,
                    decision=decision,
                    note=(
                        "The configured model returned unusable text, so the runtime "
                        "discarded it and returned this deterministic bounded plan."
                    ),
                ),
                str(model_id),
                evidence,
            )
        return f"{response_prefix}{response_text}", str(model_id), evidence

    def _planned_response(
        self,
        *,
        request: MissionRequest,
        playbook: PlaybookSpec,
        decision: PolicyDecision,
        note: str,
    ) -> str:
        """Builds a safe deterministic plan when no usable model text exists."""

        step_lines = "\n".join(
            f"{index}. {step.title}: {step.instruction}"
            for index, step in enumerate(playbook.steps, start=1)
        )
        return (
            f"{self.manifest.display_name} is ready to handle: {request.objective}\n\n"
            f"Playbook: {playbook.display_name}\n"
            f"Memory scope: {decision.memory_scope}\n"
            f"Execution plan:\n{step_lines}\n\n"
            f"{note}"
        )

    def _record_result(
        self,
        result: AgentResult,
        *,
        playbook: PlaybookSpec,
        started: float,
    ) -> None:
        for step in result.steps:
            event_type = {
                "completed": "step.completed",
                "waiting": "step.waiting",
                "blocked": "step.failed",
            }.get(step.status, "step.planned")
            self._record(
                event_type,
                summary=f"{step.title}: {step.status}",
                status=step.status,
                severity=Severity.WARNING if step.status in {"waiting", "blocked"} else Severity.INFO,
                mission_id=result.mission_id,
                work_order_id=result.work_order.id,
                run_id=result.run_id,
                subject=EntityReference(kind="playbook", id=playbook.id),
                attributes={
                    "playbook_id": playbook.id,
                    "step_id": step.step_id,
                    "step_kind": step.kind.value,
                    "effects": step.effects,
                },
            )

        duration_ms = round((perf_counter() - started) * 1000, 3)
        if result.status == MissionStatus.FAILED:
            playbook_event = "playbook.failed"
            work_event = "work_order.failed"
            specialist_event = "specialist.failed"
            severity = Severity.ERROR
        elif result.status == MissionStatus.BLOCKED:
            playbook_event = "playbook.failed"
            work_event = "work_order.blocked"
            specialist_event = "specialist.completed"
            severity = Severity.WARNING
        elif result.status == MissionStatus.AWAITING_APPROVAL:
            playbook_event = "playbook.completed"
            work_event = "work_order.blocked"
            specialist_event = "specialist.completed"
            severity = Severity.WARNING
        else:
            playbook_event = "playbook.completed"
            work_event = "work_order.completed"
            specialist_event = "specialist.completed"
            severity = Severity.INFO

        common = {
            "status": result.status.value,
            "severity": severity,
            "mission_id": result.mission_id,
            "work_order_id": result.work_order.id,
            "run_id": result.run_id,
            "duration_ms": duration_ms,
            "attributes": {
                "specialist_id": self.manifest.id,
                "playbook_id": playbook.id,
                "warning_count": len(result.warnings),
            },
        }
        self._record(
            playbook_event,
            summary=f"{playbook.display_name}: {result.status.value}",
            subject=EntityReference(kind="playbook", id=playbook.id),
            **common,
        )
        self._record(
            work_event,
            summary=f"Work order for {self.manifest.display_name}: {result.status.value}",
            **common,
        )
        self._record(
            specialist_event,
            summary=f"{self.manifest.display_name}: {result.status.value}",
            **common,
        )

    def _record(
        self,
        event_type: str,
        *,
        summary: str,
        status: str | None = None,
        severity: Severity = Severity.INFO,
        mission_id: str,
        work_order_id: str,
        run_id: str,
        subject: EntityReference | None = None,
        span_id: str | None = None,
        duration_ms: float | None = None,
        attributes: dict[str, Any] | None = None,
        metrics: dict[str, int | float | None] | None = None,
    ) -> None:
        if self.event_recorder is None:
            return
        try:
            self.event_recorder.record(
                event_type,
                summary=summary,
                status=status,
                severity=severity,
                mission_id=mission_id,
                work_order_id=work_order_id,
                run_id=run_id,
                span_id=span_id,
                actor=EntityReference(kind="specialist", id=self.manifest.id),
                subject=subject,
                duration_ms=duration_ms,
                attributes=attributes,
                metrics=metrics,
            )
        except Exception:
            return

    def _policy_subject(self) -> EntityReference:
        policy_id = self.manifest.policy_ids[0] if self.manifest.policy_ids else "default"
        return EntityReference(kind="policy", id=policy_id)

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
        models: Mapping[str, Any] | None = None,
        event_recorder: Any | None = None,
    ) -> None:
        self.registry = registry or FleetRegistry.default()
        self.llm = llm
        self.models = dict(models or {})
        self.event_recorder = event_recorder
        self.policy_engine = PolicyEngine(self.registry)
        self.wormhole = WormholeRouter(self.registry)

    def agent(
        self,
        specialist_id: str,
        *,
        llm: Any = _DEFAULT_MODEL,
    ) -> SpecialistAgent:
        """Instantiates one lightweight agent; no process is kept alive per Charter."""

        return SpecialistAgent(
            manifest=self.registry.get_specialist(specialist_id),
            registry=self.registry,
            llm=self.llm if llm is _DEFAULT_MODEL else llm,
            policy_engine=self.policy_engine,
            event_recorder=self.event_recorder,
        )

    def route(self, request: MissionRequest) -> list[RouteCandidate]:
        """Returns the selected team in execution order."""

        return self.route_plan(request).candidates

    def route_plan(self, request: MissionRequest) -> GalaxyRoutePlan:
        """Routes one Mission through the Wormhole, Galaxy, and Circles."""

        return self.wormhole.route(request)

    def run(
        self,
        request: MissionRequest,
        *,
        mission_id: str | None = None,
    ) -> FleetMissionResult:
        """Executes one safe local Mission across the routed team.

        ``mission_id`` lets an ingress layer correlate preflight work such as
        authorized Satellite calls with the same Mission timeline.  Ordinary
        callers may omit it and retain collision-resistant runtime IDs.
        """

        active_model = self._resolve_model(request)
        mission_id = mission_id or f"mission-{uuid4()}"
        mission_started = perf_counter()
        self._record_mission(
            "mission.created",
            mission_id=mission_id,
            summary="Mission created",
            status="queued",
            attributes={
                "objective_length": len(request.objective),
                "team_size": request.team_size,
                "effect_count": len(request.requested_effects),
                "model_id": request.model_id,
            },
        )
        try:
            routing = self.route_plan(request)
            candidates = routing.candidates
        except Exception as exc:
            self._record_mission(
                "mission.failed",
                mission_id=mission_id,
                summary="Mission routing failed",
                status="failed",
                severity=Severity.ERROR,
                duration_ms=round((perf_counter() - mission_started) * 1000, 3),
                attributes={"error_type": type(exc).__name__},
            )
            raise
        self._record_mission(
            "wormhole.accepted",
            mission_id=mission_id,
            summary="Wormhole accepted the Mission",
            status="accepted",
            actor=EntityReference(kind="service", id="wormhole"),
            attributes={
                "wormhole_id": routing.wormhole_id,
                "galaxy_id": routing.galaxy_id,
                "circle_count": len(routing.circles),
            },
        )
        self._record_mission(
            "galaxy.entered",
            mission_id=mission_id,
            summary=f"Entered {routing.galaxy_name}",
            status="selected",
            actor=EntityReference(kind="service", id="wormhole"),
            subject=EntityReference(kind="galaxy", id=routing.galaxy_id),
            attributes={
                "galaxy_id": routing.galaxy_id,
                "galaxy_name": routing.galaxy_name,
            },
        )
        for circle in routing.circles:
            self._record_mission(
                "circle.selected",
                mission_id=mission_id,
                summary=f"Selected Circle {circle.display_name}",
                status="selected",
                actor=EntityReference(kind="galaxy", id=routing.galaxy_id),
                subject=EntityReference(kind="guild", id=circle.circle_id),
                attributes={
                    "circle_id": circle.circle_id,
                    "score": circle.score,
                    "matched_terms": circle.matched_terms,
                    "specialist_ids": circle.selected_specialist_ids,
                },
            )
        self._record_mission(
            "mission.routed",
            mission_id=mission_id,
            summary=f"Mission routed to {len(candidates)} Specialist(s)",
            status="routed",
            attributes={
                "candidate_count": len(candidates),
                "candidate_ids": [item.specialist_id for item in candidates],
                "circle_ids": [item.circle_id for item in routing.circles],
                "wormhole_id": routing.wormhole_id,
                "galaxy_id": routing.galaxy_id,
                "matched_terms": sorted(
                    {term for item in candidates for term in item.matched_terms}
                ),
            },
        )
        self._record_mission(
            "mission.started",
            mission_id=mission_id,
            summary="Mission started",
            status="running",
        )
        results: list[AgentResult] = []
        for candidate in candidates:
            manifest = self.registry.get_specialist(candidate.specialist_id)
            requested_scope = request.memory_scope or _preferred_scope(manifest)
            permissions = PermissionGrant(
                effects=sorted(
                    set(request.requested_effects)
                    | (
                        set()
                        if request.advisory_only
                        else infer_effects(request.objective)
                    )
                ),
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
                self.agent(manifest.id, llm=active_model).run(
                    specialist_request,
                    mission_id=mission_id,
                    parent_permissions=permissions,
                )
            )
        status = _aggregate_status(results)
        warnings = [warning for result in results for warning in result.warnings]
        mission_result = FleetMissionResult(
            mission_id=mission_id,
            objective=request.objective,
            status=status,
            routing=routing,
            routed_specialists=candidates,
            results=results,
            synthesis=_synthesize(results),
            warnings=list(dict.fromkeys(warnings)),
        )
        mission_event = "mission.failed" if status == MissionStatus.FAILED else "mission.completed"
        severity = Severity.ERROR if status == MissionStatus.FAILED else (
            Severity.WARNING
            if status in {MissionStatus.BLOCKED, MissionStatus.AWAITING_APPROVAL}
            else Severity.INFO
        )
        self._record_mission(
            mission_event,
            mission_id=mission_id,
            summary=f"Mission {status.value}",
            status=status.value,
            severity=severity,
            duration_ms=round((perf_counter() - mission_started) * 1000, 3),
            attributes={
                "candidate_count": len(candidates),
                "warning_count": len(mission_result.warnings),
            },
        )
        return mission_result

    def _resolve_model(self, request: MissionRequest) -> Any | None:
        if request.model_id == "none":
            return self.llm
        if request.model_id in self.models:
            return self.models[request.model_id]
        raise ValueError(f"Model profile {request.model_id!r} is not configured.")

    def validate_all(self) -> FleetValidationReport:
        """Runs every compiled Specialist in side-effect-free planning mode."""

        validation_id = f"validation-{uuid4()}"
        mission_id = f"mission-{uuid4()}"
        started_at = datetime.now(UTC)
        started = perf_counter()
        manifests = self.registry.list_specialists()
        self._record_mission(
            "mission.created",
            mission_id=mission_id,
            summary="Fleet validation Mission created",
            status="queued",
            attributes={"team_size": len(manifests), "validation_id": validation_id},
        )
        self._record_validation(
            "fleet_validation.started",
            mission_id=mission_id,
            validation_id=validation_id,
            summary=f"Testing {len(manifests)} Specialists",
            status="running",
            attributes={"tested_count": len(manifests)},
        )
        self._record_mission(
            "mission.started",
            mission_id=mission_id,
            summary="Fleet validation started",
            status="running",
        )

        items: list[FleetValidationItem] = []
        for manifest in manifests:
            item_started = perf_counter()
            try:
                result = SpecialistAgent(
                    manifest=manifest,
                    registry=self.registry,
                    llm=None,
                    policy_engine=self.policy_engine,
                    event_recorder=self.event_recorder,
                ).run(
                    MissionRequest(
                        objective=(
                            "Prepare a bounded advisory brief from the supplied local context."
                        ),
                        specialist_id=manifest.id,
                        requested_effects=["read"],
                        allow_network=False,
                    ),
                    mission_id=mission_id,
                )
                passed = result.status in {MissionStatus.PLANNED, MissionStatus.COMPLETED}
                item = FleetValidationItem(
                    specialist_id=manifest.id,
                    specialist_name=manifest.display_name,
                    lifecycle_status=manifest.status,
                    source_status=manifest.source_status,
                    outcome=result.status,
                    passed=passed,
                    playbook_id=result.playbook_id,
                    run_id=result.run_id,
                    duration_ms=round((perf_counter() - item_started) * 1000, 3),
                    warning_count=len(result.warnings),
                )
            except Exception as exc:
                item = FleetValidationItem(
                    specialist_id=manifest.id,
                    specialist_name=manifest.display_name,
                    lifecycle_status=manifest.status,
                    source_status=manifest.source_status,
                    outcome=MissionStatus.FAILED,
                    passed=False,
                    duration_ms=round((perf_counter() - item_started) * 1000, 3),
                    error_type=type(exc).__name__,
                )
                self._record_validation(
                    "fleet_validation.agent_failed",
                    mission_id=mission_id,
                    validation_id=validation_id,
                    summary=f"Validation failed for {manifest.display_name}",
                    status="failed",
                    severity=Severity.ERROR,
                    subject=EntityReference(kind="specialist", id=manifest.id),
                    attributes={
                        "specialist_id": manifest.id,
                        "error_type": type(exc).__name__,
                    },
                )
            items.append(item)

        passed_count = sum(item.passed for item in items)
        failed_count = len(items) - passed_count
        status = "passed" if failed_count == 0 else "failed"
        duration_ms = round((perf_counter() - started) * 1000, 3)
        self._record_validation(
            "fleet_validation.completed",
            mission_id=mission_id,
            validation_id=validation_id,
            summary=f"Fleet validation {status}: {passed_count}/{len(items)} passed",
            status=status,
            severity=Severity.INFO if failed_count == 0 else Severity.ERROR,
            duration_ms=duration_ms,
            attributes={
                "tested_count": len(items),
                "passed_count": passed_count,
                "failed_count": failed_count,
            },
        )
        self._record_mission(
            "mission.completed" if failed_count == 0 else "mission.failed",
            mission_id=mission_id,
            summary=f"Fleet validation {status}",
            status="completed" if failed_count == 0 else "failed",
            severity=Severity.INFO if failed_count == 0 else Severity.ERROR,
            duration_ms=duration_ms,
            attributes={
                "tested_count": len(items),
                "passed_count": passed_count,
                "failed_count": failed_count,
                "validation_id": validation_id,
            },
        )
        finished_at = datetime.now(UTC)
        return FleetValidationReport(
            validation_id=validation_id,
            mission_id=mission_id,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            tested_count=len(items),
            passed_count=passed_count,
            failed_count=failed_count,
            results=items,
        )

    def _record_mission(
        self,
        event_type: str,
        *,
        mission_id: str,
        summary: str,
        status: str,
        severity: Severity = Severity.INFO,
        duration_ms: float | None = None,
        attributes: dict[str, Any] | None = None,
        actor: EntityReference | None = None,
        subject: EntityReference | None = None,
    ) -> None:
        if self.event_recorder is None:
            return
        try:
            self.event_recorder.record(
                event_type,
                summary=summary,
                status=status,
                severity=severity,
                mission_id=mission_id,
                actor=actor or EntityReference(kind="service", id="fleet_runtime"),
                subject=subject,
                duration_ms=duration_ms,
                attributes=attributes,
            )
        except Exception:
            return

    def _record_validation(
        self,
        event_type: str,
        *,
        mission_id: str,
        validation_id: str,
        summary: str,
        status: str,
        severity: Severity = Severity.INFO,
        subject: EntityReference | None = None,
        duration_ms: float | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        if self.event_recorder is None:
            return
        try:
            self.event_recorder.record(
                event_type,
                summary=summary,
                status=status,
                severity=severity,
                mission_id=mission_id,
                actor=EntityReference(kind="service", id="fleet_runtime"),
                subject=subject,
                duration_ms=duration_ms,
                attributes={"validation_id": validation_id, **(attributes or {})},
            )
        except Exception:
            return


def _preferred_scope(manifest: SpecialistManifest) -> str:
    for preferred in ("employer_authorized", "personal", "exploration", "long_term", "working"):
        if preferred in manifest.memory_scope_ids:
            return preferred
    return manifest.memory_scope_ids[0]


_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
_CONTROL_CHARACTER_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _assess_generation_quality(
    text: str,
    *,
    finish_reason: str | None,
    response_prefix: str,
    objective: str,
) -> tuple[str, list[str]]:
    """Applies cheap, explainable checks without claiming semantic correctness."""

    checks: list[str] = []
    if _HTML_TAG_RE.search(text):
        checks.append("contains_html_markup")
    if _CONTROL_CHARACTER_RE.search(text):
        checks.append("contains_control_characters")
    if response_prefix and response_prefix.lower() in text.lower():
        checks.append("repeats_prompt_prefix")
    if finish_reason in {"length", "max_tokens"}:
        checks.append("truncated_by_token_limit")
    words = re.findall(r"[a-z0-9']+", text.lower())
    if len(words) < 4:
        checks.append("too_short")
    if len(words) >= 24 and len(set(words)) / len(words) < 0.28:
        checks.append("high_repetition")
    objective_lower = objective.lower()
    if re.search(r"\b(?:concise|brief|short)\b", objective_lower) and len(words) > 100:
        checks.append("exceeds_requested_brevity")
    if re.search(
        r"\b(?:one|1)\s+(?:concise\s+|short\s+|small\s+)?"
        r"(?:idea|step|action|recommendation|option|suggestion)\b",
        objective_lower,
    ):
        enumerated_items = re.findall(r"(?:^|\s)(?:\d+[.)]|[-*])\s+", text)
        if len(enumerated_items) > 1:
            checks.append("violates_single_item_request")
    requested_sentences = _requested_sentence_count(objective_lower)
    if requested_sentences is not None:
        actual_sentences = len(re.findall(r"[.!?]+(?:\s|$)", text.strip()))
        if actual_sentences != requested_sentences:
            checks.append("sentence_count_mismatch")
    rejected_checks = {
        "contains_control_characters",
        "exceeds_requested_brevity",
        "repeats_prompt_prefix",
        "sentence_count_mismatch",
        "too_short",
        "high_repetition",
        "violates_single_item_request",
    }
    if rejected_checks.intersection(checks):
        return "rejected", checks
    return ("degraded" if checks else "accepted", checks)


def _requested_sentence_count(objective: str) -> int | None:
    """Extracts only explicit small sentence-count constraints from a Mission."""

    match = re.search(
        r"\b(one|two|three|[1-3])\s+(?:short\s+|concise\s+)?sentences?\b",
        objective,
    )
    if match is None:
        return None
    value = match.group(1)
    if value.isdigit():
        return int(value)
    return {"one": 1, "two": 2, "three": 3}[value]


def _optional_nonnegative_int(value: Any) -> int | None:
    """Normalizes portable token counters reported by model clients."""

    if value is None or isinstance(value, bool):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized >= 0 else None


def _optional_text(value: Any) -> str | None:
    """Normalizes optional completion metadata without inventing values."""

    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


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
