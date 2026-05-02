"""Collection Agent demo with plan loop and mode switching."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from agents.collection_memory_helper_agent.repository import CollectionMemoryRepository
from agents.collection_agent.nodes import CollectionIntentNode, CollectionReflectNode, CollectionResponseNode, PlanProposalNode
from agents.collection_agent.planner import CollectionPlanner
from agents.collection_agent.prompts import load_collection_agent_prompts, render_collection_tool_catalog_yaml
from agents.collection_agent.repository import CollectionRepository
from agents.collection_agent.state import CollectionGraphState
from agents.collection_agent.tools import (
    CaseFetchTool,
    CasePrioritizeTool,
    ChannelSwitchTool,
    ContactAttemptTool,
    CustomerVerifyTool,
    DispositionUpdateTool,
    DuesExplainBuildTool,
    FollowupScheduleTool,
    HumanEscalationTool,
    LoanPolicyLookupTool,
    OfferEligibilityTool,
    PayByPhoneCollectTool,
    PaymentLinkCreateTool,
    PaymentStatusCheckTool,
    PlanProposeTool,
    PromiseCaptureTool,
)
from agents.collection_agent.tools.data_store import CollectionDataStore
from src.agents.base_agent import BaseAgent
from src.memory.session_store import SessionStore
from src.memory.types import WorkingMemory
from src.nodes.memory_retrieve_node import MemoryRetrieveNode
from src.nodes.react_node import ReactNode
from src.nodes.tool_execution_node import ToolExecutionNode
from src.nodes.types import AgentState
from src.platform_logging.tracing import ExecutionTrace, emit_trace_event, trace_node, trace_turn
from src.tools.executor import ToolExecutor
from src.tools.registry import ToolRegistry


@dataclass(slots=True)
class CollectionAgent(BaseAgent):
    """Runs the collections demo graph with plan proposal loop."""

    repository: CollectionRepository
    data_store: CollectionDataStore
    llm: Any | None = None
    session_store: SessionStore | None = None
    tool_registry: ToolRegistry | None = None
    tool_executor: ToolExecutor | None = None
    planner: CollectionPlanner | None = None
    logger: Any | None = None
    trace_sink: Any | None = None
    trace_output_dir: Path | None = None
    memory_repository: CollectionMemoryRepository | None = None
    agent_name: str = "collection_agent"
    last_trace: ExecutionTrace | None = None

    def __post_init__(self) -> None:
        prompts = load_collection_agent_prompts()
        intent_prompts = prompts.get("intent", {})
        react_prompts = prompts.get("react", {})
        reflect_prompts = prompts.get("reflect", {})
        response_prompts = prompts.get("response", {})

        BaseAgent.__init__(
            self,
            llm=self.llm,
            agent_name=self.agent_name,
            logger=self.logger,
            trace_sink=self.trace_sink,
        )
        self.session_store = self.session_store or SessionStore(self.repository)
        self.memory_repository = self.memory_repository or CollectionMemoryRepository(
            collection_runtime_dir=self.repository.runtime_dir
        )
        self.tool_registry = self.tool_registry or self._build_tool_registry()
        self.tool_executor = self.tool_executor or ToolExecutor(
            registry=self.tool_registry,
            repository=self.repository,
            memory_store=None,
            memory_policy=None,
        )
        self.planner = self.planner or CollectionPlanner(
            llm=self.llm,
            intent_system_prompt=str(intent_prompts.get("system_prompt", "")),
            intent_user_prompt=str(intent_prompts.get("user_prompt", "")),
        )

        self.memory_retrieve_node = MemoryRetrieveNode(tool_registry=self.tool_registry, memories=[WorkingMemory])
        self.relevance_intent_node = CollectionIntentNode(
            llm=self.llm,
            system_prompt=str(intent_prompts.get("relevance_system_prompt", "")),
            user_prompt=str(intent_prompts.get("relevance_user_prompt", "")),
            output_key="relevance_intent",
            intent_labels=["relevant", "irrelevant", "empty"],
            default_intent="irrelevant",
            default_confidence=0.3,
            route_map={
                "relevant": "relevant",
                "irrelevant": "irrelevant",
                "empty": "empty",
                "unknown": "irrelevant",
            },
            default_route="irrelevant",
            empty_input_intent="empty",
            fallback_keyword_map={
                "relevant": [
                    "collections",
                    "collection",
                    "loan",
                    "dues",
                    "emi",
                    "overdue",
                    "defaulter",
                    "default",
                    "payment",
                    "pay",
                    "repay",
                    "policy",
                    "verify",
                    "hardship",
                    "discount",
                    "settlement",
                    "follow up",
                    "followup",
                    "case",
                    "promise",
                    "waiver",
                    "restructure",
                    "bye",
                    "goodbye",
                    "end conversation",
                    "that's all",
                ]
            },
            response_map={
                "empty": "No input was provided. Please share a collections-related query such as dues, EMI, payment, verification, or repayment plan.",
                "irrelevant": "This request is outside collections scope. I can only help with loan dues, EMI, payments, verification, hardship plans, and follow-ups.",
                "unknown": "This request is outside collections scope. I can only help with loan dues, EMI, payments, verification, hardship plans, and follow-ups.",
            },
        )
        self.pre_plan_intent_node = CollectionIntentNode(
            llm=self.llm,
            system_prompt=str(intent_prompts.get("pre_plan_system_prompt", "")),
            user_prompt=str(intent_prompts.get("pre_plan_user_prompt", "")),
            output_key="pre_plan_intent",
            intent_labels=["plan", "decide"],
            default_intent="decide",
            default_confidence=0.4,
            route_map={
                "plan": "plan",
                "decide": "decide",
                "unknown": "decide",
            },
            default_route="decide",
            fallback_keyword_map={
                "plan": [
                    "what can you do",
                    "help",
                    "explain",
                    "overview",
                    "summary",
                    "process",
                    "steps",
                    "policy",
                    "dues explanation",
                ]
            },
        )
        self.execution_path_intent_node = CollectionIntentNode(
            llm=self.llm,
            system_prompt=str(intent_prompts.get("execution_path_system_prompt", "")),
            user_prompt=str(intent_prompts.get("execution_path_user_prompt", "")),
            output_key="execution_path_intent",
            intent_labels=["need_memory", "need_tool"],
            default_intent="need_tool",
            default_confidence=0.4,
            route_map={
                "need_memory": "need_memory",
                "need_tool": "need_tool",
                "unknown": "need_tool",
            },
            default_route="need_tool",
            fallback_keyword_map={
                "need_memory": [
                    "previous",
                    "last call",
                    "history",
                    "already promised",
                    "promise date",
                    "existing plan",
                    "follow up",
                    "follow-up",
                    "status of my case",
                ]
            },
        )
        self.post_memory_plan_intent_node = CollectionIntentNode(
            llm=self.llm,
            system_prompt=str(intent_prompts.get("post_memory_plan_system_prompt", "")),
            user_prompt=str(intent_prompts.get("post_memory_plan_user_prompt", "")),
            output_key="post_memory_plan_intent",
            intent_labels=["plan", "react"],
            default_intent="react",
            default_confidence=0.4,
            route_map={
                "plan": "plan",
                "react": "react",
                "unknown": "react",
            },
            default_route="react",
            fallback_keyword_map={
                "plan": [
                    "explain",
                    "summarize",
                    "respond",
                    "clarify",
                    "policy",
                    "dues breakdown",
                ]
            },
        )
        self.react_node = ReactNode(
            planner=self.planner,
            llm=self.llm,
            system_prompt=str(react_prompts.get("system_prompt", "")),
            user_prompt=str(react_prompts.get("user_prompt", "{user_input}")),
            available_tools=render_collection_tool_catalog_yaml(),
            max_steps=8,
        )
        self.plan_node = PlanProposalNode(llm=self.llm)
        self.tool_execution_node = ToolExecutionNode(executor=self.tool_executor)
        self.reflect_node = CollectionReflectNode(
            llm=self.llm,
            system_prompt=str(reflect_prompts.get("system_prompt", "")),
            complete_route="complete",
            incomplete_route="incomplete",
            merge_feedback_into_observation=True,
            emit_memory_update=False,
        )
        self.relevant_response_node = CollectionResponseNode(
            llm=self.llm,
            system_prompt=str(response_prompts.get("system_prompt", "")),
            user_prompt=str(response_prompts.get("user_prompt", "{observation}")),
            default_response="No action selected.",
            default_target="customer",
        )
        self.irrelevant_response_node = CollectionResponseNode(
            llm=None,
            system_prompt="",
            user_prompt="{response}",
            default_response="This request is outside collections scope. I can only help with loan dues, EMI, payments, verification, hardship plans, and follow-ups.",
            default_target="customer",
        )
        self.graph = self._build_graph()

    def _build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(CaseFetchTool(store=self.data_store))
        registry.register(CasePrioritizeTool(store=self.data_store))
        registry.register(ContactAttemptTool(store=self.data_store))
        registry.register(CustomerVerifyTool(store=self.data_store))
        registry.register(LoanPolicyLookupTool(store=self.data_store))
        registry.register(DuesExplainBuildTool(store=self.data_store))
        registry.register(OfferEligibilityTool(store=self.data_store))
        registry.register(PaymentLinkCreateTool(store=self.data_store))
        registry.register(PaymentStatusCheckTool(store=self.data_store))
        registry.register(PromiseCaptureTool(store=self.data_store))
        registry.register(FollowupScheduleTool(store=self.data_store))
        registry.register(DispositionUpdateTool(store=self.data_store))
        registry.register(HumanEscalationTool(store=self.data_store))
        registry.register(ChannelSwitchTool(store=self.data_store))
        registry.register(PayByPhoneCollectTool(store=self.data_store))
        registry.register(PlanProposeTool(store=self.data_store))
        return registry

    def _build_graph(self) -> Any:
        graph = StateGraph(CollectionGraphState)
        graph.add_node("relevance_intent", self._wrap_node("relevance_intent", self.relevance_intent_node.execute))
        graph.add_node("pre_plan_intent", self._wrap_node("pre_plan_intent", self.pre_plan_intent_node.execute))
        graph.add_node(
            "execution_path_intent", self._wrap_node("execution_path_intent", self.execution_path_intent_node.execute)
        )
        graph.add_node("memory_retrieve", self._wrap_node("memory_retrieve", self.memory_retrieve_node.execute))
        graph.add_node(
            "post_memory_plan_intent",
            self._wrap_node("post_memory_plan_intent", self.post_memory_plan_intent_node.execute),
        )
        graph.add_node(
            "origin_pre_plan",
            self._wrap_node(
                "origin_pre_plan",
                lambda _state: {"routing_context": {"plan_origin": "pre_plan_intent"}},
            ),
        )
        graph.add_node(
            "origin_post_memory_plan",
            self._wrap_node(
                "origin_post_memory_plan",
                lambda _state: {"routing_context": {"plan_origin": "post_memory_plan_intent"}},
            ),
        )
        graph.add_node(
            "origin_react_plan",
            self._wrap_node(
                "origin_react_plan",
                lambda _state: {"routing_context": {"plan_origin": "react"}},
            ),
        )
        graph.add_node("react", self._wrap_node("react", self.react_node.execute))
        graph.add_node("plan_proposal", self._wrap_node("plan_proposal", self.plan_node.execute))
        graph.add_node("tool_execution", self._wrap_node("tool_execution", self.tool_execution_node.execute))
        graph.add_node("reflect", self._wrap_node("reflect", self.reflect_node.execute))
        graph.add_node("relevant_response", self._wrap_node("relevant_response", self.relevant_response_node.execute))
        graph.add_node(
            "irrelevant_response", self._wrap_node("irrelevant_response", self.irrelevant_response_node.execute)
        )

        graph.add_edge(START, "relevance_intent")
        graph.add_conditional_edges(
            "relevance_intent",
            self.relevance_intent_node.route,
            {
                "relevant": "pre_plan_intent",
                "irrelevant": "irrelevant_response",
                "empty": "irrelevant_response",
            },
        )
        graph.add_conditional_edges(
            "pre_plan_intent",
            self.pre_plan_intent_node.route,
            {
                "plan": "origin_pre_plan",
                "decide": "execution_path_intent",
            },
        )
        graph.add_conditional_edges(
            "execution_path_intent",
            self.execution_path_intent_node.route,
            {
                "need_memory": "memory_retrieve",
                "need_tool": "react",
            },
        )
        graph.add_edge("memory_retrieve", "post_memory_plan_intent")
        graph.add_conditional_edges(
            "post_memory_plan_intent",
            self.post_memory_plan_intent_node.route,
            {
                "plan": "origin_post_memory_plan",
                "react": "react",
            },
        )
        graph.add_edge("origin_pre_plan", "plan_proposal")
        graph.add_edge("origin_post_memory_plan", "plan_proposal")
        graph.add_edge("origin_react_plan", "plan_proposal")
        graph.add_conditional_edges(
            "react",
            self.react_node.route,
            {
                "act": "tool_execution",
                "respond": "origin_react_plan",
                "end": "origin_react_plan",
            },
        )
        graph.add_conditional_edges(
            "plan_proposal",
            self.plan_node.route,
            {
                "propose": "tool_execution",
                "continue": "reflect",
            },
        )
        graph.add_edge("tool_execution", "react")
        graph.add_conditional_edges(
            "reflect",
            self.reflect_node.route,
            {
                "retry_react": "react",
                "retry_plan_proposal": "plan_proposal",
                "complete": "relevant_response",
            },
        )
        graph.add_edge("relevant_response", END)
        graph.add_edge("irrelevant_response", END)
        return graph.compile()

    def _wrap_node(self, node_name: str, fn: Any) -> Any:
        def _wrapped(state: CollectionGraphState) -> CollectionGraphState:
            trace_state = {k: v for k, v in state.items() if k != "memory"}
            with trace_node(node_name, state=trace_state):
                result = fn(state)
            if isinstance(result, dict):
                history = list(state.get("node_history", []))
                result["node_history"] = [*history, node_name]
                result.setdefault("conversation_phase", self._phase_for_node(node_name))
            emit_trace_event(
                {
                    "event": "node_state",
                    "node_name": node_name,
                    "step": state.get("steps", 0),
                    "decision": repr(state.get("decision")),
                    "observation": result.get("observation") if isinstance(result, dict) else None,
                    "response": result.get("response") if isinstance(result, dict) else None,
                    "route": result.get("route") if isinstance(result, dict) else None,
                }
            )
            return result

        return _wrapped

    def run_turn(self, user_input: str, session_id: str | None = None) -> AgentState:
        session_key = session_id or "collection-demo-session"
        memory = self.session_store.load(session_key)
        if "mode" not in memory.state:
            memory.set_state(mode="strict_collections", active_channel="sms", active_case_id="COLL-1001")
        turn_index = int(memory.state.get("turn_index", 0))
        self._sync_user_and_memory_context(memory=memory, user_input=user_input)
        user_id = str(memory.state.get("active_user_id", "")).strip()
        case_id = str(memory.state.get("active_case_id", "COLL-1001")).strip()
        channel = str(memory.state.get("active_channel", "sms")).strip()
        trace = ExecutionTrace(agent_name=self.agent_name, session_id=session_key, user_input=user_input)
        try:
            with trace_turn(trace, sink=self.trace_sink):
                state = self.graph.invoke(
                    {
                        "session_id": session_key,
                        "turn_id": str(uuid4()),
                        "user_input": user_input,
                        "memory": memory,
                        "user_id": user_id,
                        "case_id": case_id,
                        "channel": channel,
                        "memory_targets": [{"type": "working", "enabled": True, "limit": 8}],
                        "observation": None,
                        "node_history": [],
                        "conversation_phase": "turn_started",
                        "tool_errors": [],
                        "steps": 0,
                        "turn_index": turn_index,
                    }
                )
                state = self._finalize_output_state(state)
                memory.set_state(
                    turn_index=turn_index + 1,
                    last_user_input=user_input,
                    last_agent_response=str(state.get("response", "")).strip(),
                    last_response_target=str(state.get("response_target", "customer")).strip().lower() or "customer",
                )
                trace.finish(status="completed")
        except Exception as exc:
            trace.finish(status="failed", error=str(exc))
            self.last_trace = trace
            self._persist_trace(trace)
            raise
        self.last_trace = trace
        self._persist_trace(trace)
        return state

    def run(self, user_input: str, session_id: str | None = None) -> str:
        state = self.run_turn(user_input=user_input, session_id=session_id)
        return str(state.get("response", "No response generated."))

    def _finalize_output_state(self, state: AgentState) -> AgentState:
        """Guarantees output contract keys for downstream orchestration."""
        output = dict(state)
        response_target = str(output.get("response_target", "customer")).strip().lower()
        if response_target not in {"customer", "self", "discount_planning_agent"}:
            response_target = "customer"
        output["response_target"] = response_target

        response = output.get("response")
        if not isinstance(response, str) or not response.strip():
            plan = output.get("plan_proposal") if isinstance(output.get("plan_proposal"), dict) else {}
            planned = str(plan.get("draft_response", "")).strip() if plan else ""
            if planned:
                output["response"] = planned
            else:
                decision = output.get("decision")
                decision_text = str(getattr(decision, "response_text", "")).strip() if decision is not None else ""
                fallback_outline = str(plan.get("plan_outline", "")).strip() if plan else ""
                output["response"] = decision_text or fallback_outline or "No response generated."
        return output

    def _persist_trace(self, trace: ExecutionTrace) -> None:
        target_dir = self.trace_output_dir
        if target_dir is None:
            return
        target_dir.mkdir(parents=True, exist_ok=True)
        payload = trace.to_dict()
        timestamp = trace.started_at.strftime("%Y%m%dT%H%M%S")
        trace_path = target_dir / f"{timestamp}_{trace.trace_id}.json"
        trace_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        latest_path = target_dir / "latest_trace.json"
        latest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    @classmethod
    def from_local_files(cls, base_dir: Path | None = None) -> "CollectionAgent":
        root = base_dir or Path(__file__).resolve().parent
        repository = CollectionRepository(runtime_dir=root / "runtime")
        data_store = CollectionDataStore(base_dir=root)
        return cls(repository=repository, data_store=data_store, trace_output_dir=root / "runtime" / "traces")

    def _sync_user_and_memory_context(self, *, memory: Any, user_input: str) -> None:
        case_match = re.search(r"(COLL-\d+)", user_input, re.IGNORECASE)
        if case_match:
            memory.set_state(active_case_id=case_match.group(1).upper())
        user_id = self._resolve_user_id(memory_state=dict(memory.state), user_input=user_input)
        if user_id:
            memory.set_state(active_user_id=user_id)
        self._hydrate_case_context(memory=memory)
        global_context = self.memory_repository.get_global_memory_context(limit=6) if self.memory_repository else {}
        user_context = (
            self.memory_repository.get_user_memory_context(user_id) if self.memory_repository and user_id else None
        )
        memory.set_state(
            global_key_event_memory=global_context,
            user_key_event_memory=(user_context or {}),
        )

    def _hydrate_case_context(self, *, memory: Any) -> None:
        memory_state = dict(memory.state)
        active_case_id = str(memory_state.get("active_case_id", "")).strip()
        active_user_id = str(memory_state.get("active_user_id", "")).strip()

        case_row = self.data_store.get_case(case_id=active_case_id) if active_case_id else None
        if not case_row and active_user_id:
            case_row = self.data_store.get_case(customer_id=active_user_id)

        customer_id = active_user_id
        if isinstance(case_row, dict):
            customer_id = str(case_row.get("customer_id", customer_id)).strip()
            memory.set_state(
                active_case_id=str(case_row.get("case_id", active_case_id or "COLL-1001")).strip().upper(),
                active_overdue_amount=float(case_row.get("overdue_amount", 0.0) or 0.0),
                active_emi_amount=float(case_row.get("emi_amount", 0.0) or 0.0),
                active_late_fee=float(case_row.get("late_fee", 0.0) or 0.0),
                active_dpd=int(case_row.get("dpd", 0) or 0),
                active_loan_id=str(case_row.get("loan_id", "")).strip(),
            )
            if customer_id:
                memory.set_state(active_user_id=customer_id)

        if customer_id:
            customer_row = self.data_store.get_customer(customer_id)
            if isinstance(customer_row, dict):
                memory.set_state(
                    active_customer_name=str(customer_row.get("name", memory_state.get("active_customer_name", "Customer")))
                    .strip()
                    or "Customer",
                    active_customer_phone=str(customer_row.get("phone", "")).strip(),
                    active_customer_email=str(customer_row.get("email", "")).strip(),
                )

    def _resolve_user_id(self, *, memory_state: dict[str, Any], user_input: str) -> str | None:
        from_state = memory_state.get("active_user_id") or memory_state.get("user_id")
        if from_state is not None and str(from_state).strip():
            return str(from_state).strip()

        customer_match = re.search(r"(CUST-\d+)", user_input, re.IGNORECASE)
        if customer_match:
            return customer_match.group(1).upper()

        case_match = re.search(r"(COLL-\d+)", user_input, re.IGNORECASE)
        case_id = case_match.group(1).upper() if case_match else str(memory_state.get("active_case_id", "")).upper()
        if case_id:
            case_row = self.data_store.get_case(case_id=case_id)
            if isinstance(case_row, dict) and case_row.get("customer_id"):
                return str(case_row["customer_id"])
        return None

    @staticmethod
    def _phase_for_node(node_name: str) -> str:
        phase_map = {
            "relevance_intent": "relevance_classification",
            "pre_plan_intent": "pre_plan_routing",
            "execution_path_intent": "execution_routing",
            "memory_retrieve": "memory_hydration",
            "post_memory_plan_intent": "post_memory_routing",
            "react": "action_planning",
            "tool_execution": "tool_execution",
            "plan_proposal": "plan_proposal",
            "reflect": "quality_reflection",
            "relevant_response": "response_packaging",
            "irrelevant_response": "response_packaging",
        }
        return phase_map.get(node_name, "graph_processing")


__all__ = ["CollectionAgent"]
