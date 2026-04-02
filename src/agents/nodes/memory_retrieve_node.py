"""Created: 2026-03-31

Purpose: Implements the reusable memory retrieval node for shared agent graphs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.agents.nodes.base import BaseGraphNode
from src.agents.nodes.types import AgentState, NodeUpdate
from src.memory.models import RetrievalContext
from src.memory.types import EpisodicMemory, ProceduralMemory, SemanticMemory, WorkingMemory
from src.tools.registry import ToolRegistry


@dataclass(slots=True)
class MemoryRetrieveNode(BaseGraphNode):
    """Builds the structured memory context for the current agent turn.

    This node gathers the four runtime memory inputs expected by the shared
    planner flow:

    - semantic memory retrieved from long-term memory
    - episodic memory retrieved from long-term memory
    - working memory derived from the active session state
    - procedural memory derived from the available tools and planner identity

    It is intentionally generic and does not embed MailMind-specific logic.
    """

    tool_registry: ToolRegistry
    llm: Any | None = None
    memory_retriever: Any | None = None
    memories: list[Any] | None = None
    system_prompt: str | None = None
    user_prompt: str | None = None

    def plan(
        self,
        *,
        user_input: str,
        memory: Any | None = None,
        memory_context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        user_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Builds a memory retrieval plan for the current turn.

        If an LLM and prompts are configured, the model can choose which memory
        targets to retrieve and with what limits. Otherwise the node retrieves
        all configured memory targets using conservative defaults.
        """
        default_plan = self._default_plan(memory=memory)
        if self.llm is None:
            return default_plan
        rendered_user_prompt = self._render_user_prompt(
            user_prompt=user_prompt if user_prompt is not None else (self.user_prompt or "{user_input}"),
            user_input=user_input,
            memory=memory,
            memory_context=memory_context,
            memory_targets=self._memory_targets(),
        )
        raw = self.llm.generate(system_prompt or self.system_prompt or "", rendered_user_prompt).strip()
        planned = self._parse_plan(raw)
        return planned or default_plan

    def execute(self, state: AgentState) -> NodeUpdate:
        """Builds and stores the memory context for the current turn.

        Args:
            state: The current shared graph state.

        Returns:
            A partial state update containing the assembled memory context.
        """
        self._record_llm_usage(state, node_name="memory_retrieve")
        user_input = state["user_input"]
        memory = state["memory"]
        memory_state = dict(getattr(memory, "state", {}))
        context = RetrievalContext(
            agent_id=str(memory_state.get("agent_id", "mailmind")),
            step_count=state.get("steps", 0),
            confidence=float(state.get("confidence", 1.0) or 1.0),
            last_error=bool(memory_state.get("last_error", False)),
        )
        retrieval_plan = self.plan(
            user_input=user_input,
            memory=memory,
            memory_context=state.get("memory_context"),
            system_prompt=self.system_prompt,
            user_prompt=self.user_prompt,
        )
        assembled_context: dict[str, Any] = {}
        for item in retrieval_plan:
            target = str(item.get("target", "")).lower()
            limit = int(item.get("limit", 5))
            if target == "working":
                assembled_context["working"] = self._build_working_memory(memory, user_input)
                continue
            if target == "procedural":
                assembled_context["procedural"] = self._build_procedural_memory()
                continue
            if self.memory_retriever is None:
                assembled_context[target] = []
                continue
            assembled_context[target] = self._retrieve(
                user_input,
                filters=self._filters_for_target(target, context),
                limit=limit,
                context=context,
            )
        return {"memory_context": assembled_context}

    def _default_plan(self, *, memory: Any | None) -> list[dict[str, Any]]:
        """Builds the default retrieval plan for configured memory targets."""
        del memory
        return [
            {"target": target, "limit": 5}
            for target in self._memory_targets()
        ]

    def _memory_targets(self) -> list[str]:
        """Normalizes constructor-provided memory targets into target names."""
        configured = self.memories or [SemanticMemory, EpisodicMemory, WorkingMemory, ProceduralMemory]
        targets: list[str] = []
        for memory in configured:
            if memory is WorkingMemory or getattr(memory, "__name__", None) == "WorkingMemory":
                targets.append("working")
                continue
            if memory is ProceduralMemory or getattr(memory, "__name__", None) == "ProceduralMemory":
                targets.append("procedural")
                continue
            memory_type = getattr(getattr(memory, "model_fields", {}), "get", lambda *_: None)("type")
            if memory_type is not None:
                targets.append(str(memory_type.default))
                continue
            if hasattr(memory, "type"):
                targets.append(str(getattr(memory, "type")))
        return targets

    @staticmethod
    def _build_working_memory(memory: Any | None, user_input: str) -> WorkingMemory:
        """Builds a working-memory snapshot from the current graph memory."""
        session_id = getattr(memory, "session_id", "unknown")
        recent_items = list(getattr(memory, "recent_items", []))
        if not recent_items and hasattr(memory, "history"):
            recent_items = [
                {"role": message.role, "content": message.content}
                for message in getattr(memory, "history", [])[-6:]
            ]
        return WorkingMemory(
            session_id=session_id,
            current_goal=user_input,
            state=dict(getattr(memory, "state", {})),
            recent_items=recent_items,
        )

    def _build_procedural_memory(self) -> ProceduralMemory:
        """Builds procedural memory from the configured planner, tools, and LLM."""
        return ProceduralMemory(
            tool_names=[tool.name for tool in self.tool_registry.list_tools()],
            planner_names=[],
            llm_names=[] if self._llm_name() is None else [self._llm_name()],
            prompt_names=[],
        )

    @staticmethod
    def _filters_for_target(target: str, context: RetrievalContext) -> dict[str, object]:
        """Builds retrieval filters for one long-term memory target."""
        return {"type": target, "agent_id": context.agent_id}

    def _retrieve(
        self,
        query: str,
        *,
        filters: dict[str, object],
        limit: int,
        context: RetrievalContext,
    ) -> list[Any]:
        """Calls either a context-aware router or a legacy local retriever."""
        try:
            return self.memory_retriever.retrieve(query, filters=filters, limit=limit, context=context)
        except TypeError:
            return self.memory_retriever.retrieve(query, filters=filters, limit=limit)

    @staticmethod
    def _parse_plan(raw: str) -> list[dict[str, Any]]:
        """Parses an LLM-produced memory retrieval plan from JSON output."""
        candidate = raw.strip()
        match = re.search(r"(\{.*\}|\[.*\])", candidate, re.DOTALL)
        if match is not None:
            candidate = match.group(1)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, dict):
            items = parsed.get("memory_retrievals", [])
            return [item for item in items if isinstance(item, dict)]
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        return []

    @staticmethod
    def _render_user_prompt(
        *,
        user_prompt: str,
        user_input: str,
        memory: Any | None,
        memory_context: dict[str, Any] | None,
        memory_targets: list[str],
    ) -> str:
        """Renders retrieval-planning context into the prompt template."""
        values = {
            "user_input": user_input,
            "memory": json.dumps(getattr(memory, "state", {}), default=str, ensure_ascii=True) if memory is not None else None,
            "memory_context": json.dumps(memory_context, default=str, ensure_ascii=True) if memory_context is not None else None,
            "memory_targets": json.dumps(memory_targets, ensure_ascii=True) if memory_targets else None,
        }
        rendered_lines: list[str] = []
        for line in user_prompt.splitlines():
            rendered_line = line
            skip_line = False
            for key, value in values.items():
                placeholder = f"{{{key}}}"
                if placeholder not in rendered_line:
                    continue
                if value is None:
                    skip_line = True
                    break
                rendered_line = rendered_line.replace(placeholder, value)
            if skip_line:
                continue
            if re.search(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", rendered_line):
                continue
            rendered_lines.append(rendered_line)
        return "\n".join(rendered_lines).strip() or user_prompt
