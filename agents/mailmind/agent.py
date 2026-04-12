"""Created: 2026-04-11

Purpose: Implements the MailMind agent graph from the MailMind graph spec.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from agents.mailmind.nodes import MailMindApprovalRouterNode, MailMindEntryRouterNode
from agents.mailmind.prompts import load_mailmind_agent_prompts, render_mailmind_tool_catalog_yaml
from agents.mailmind.tools import MailMindSummaryTool
from src.agents.base_agent import BaseAgent
from src.interfaces.email import ApprovalQueue, EmailSender, EmailSource, MessageClassifier, MessageRepository, Notifier
from src.interfaces.whatsapp import WhatsAppInterface
from src.memory.base import BaseMemoryStore
from src.memory.session_store import SessionStore
from src.memory.types import EpisodicMemory, ReflectionMemory, SemanticMemory, WorkingMemory
from src.nodes import AgentState, IntentNode, MemoryNode, MemoryRetrieveNode, ReflectNode, ResponseNode, ToolExecutionNode, WhatsAppNode
from src.nodes.react_node import ReactNode
from src.platform_logging.tracing import ExecutionTrace, trace_turn
from src.tools.executor import ToolExecutor
from src.tools.gmail import (
    DraftReplyTool,
    EmailClassifierTool,
    EmailSearchTool,
    EmailSendTool,
    EmailSummaryTool,
    GmailFetchTool,
    NotificationTool,
)
from src.tools.memory_search import MemorySearchTool
from src.tools.memory_write import MemoryWriteTool
from src.tools.registry import ToolRegistry


@dataclass(slots=True)
class MailMindAgent(BaseAgent):
    """Runs the MailMind graph using shared platform nodes plus MailMind routers."""

    repository: MessageRepository
    whatsapp: WhatsAppInterface
    llm: Any | None = None
    source: EmailSource | None = None
    classifier: MessageClassifier | None = None
    notifier: Notifier | None = None
    sender: EmailSender | None = None
    approval_queue: ApprovalQueue | None = None
    session_store: SessionStore | None = None
    tool_registry: ToolRegistry | None = None
    tool_executor: ToolExecutor | None = None
    memory_store: BaseMemoryStore | None = None
    memory_retriever: Any | None = None
    intent_llm: Any | None = None
    react_llm: Any | None = None
    reflect_llm: Any | None = None
    response_llm: Any | None = None
    logger: Any | None = None
    trace_sink: Any | None = None
    agent_name: str = "mailmind"

    def __post_init__(self) -> None:
        runtime_llm = self.react_llm or self.llm
        prompt_bundle = load_mailmind_agent_prompts()
        tool_catalog_prompt = render_mailmind_tool_catalog_yaml()
        intent_prompts = prompt_bundle.get("intent", {})
        react_prompts = prompt_bundle.get("react", {})
        reflect_prompts = prompt_bundle.get("reflect", {})
        response_prompts = prompt_bundle.get("response", {})
        intent_labels = list(intent_prompts.get("labels", ["poll_inbox", "query_mail", "approval_reply", "maintenance"]))
        BaseAgent.__init__(
            self,
            llm=runtime_llm,
            agent_name=self.agent_name,
            logger=self.logger,
            trace_sink=self.trace_sink,
        )
        self.session_store = self.session_store or SessionStore(self.repository)
        self.tool_registry = self.tool_registry or self._build_tool_registry()
        self.tool_executor = self.tool_executor or ToolExecutor(
            registry=self.tool_registry,
            repository=self.repository,
            memory_store=self.memory_store,
            memory_policy=None,
        )
        self.intent_node = IntentNode(
            llm=self.intent_llm or runtime_llm,
            system_prompt=str(intent_prompts.get("system_prompt", "")),
            user_prompt=str(intent_prompts.get("user_prompt", "{user_input}")),
            intent_labels=intent_labels,
            default_intent="query_mail",
            default_confidence=0.25,
        )
        self.entry_router = MailMindEntryRouterNode()
        self.approval_router = MailMindApprovalRouterNode()
        self.memory_retrieve_node = MemoryRetrieveNode(
            tool_registry=self.tool_registry,
            memory_retriever=self.memory_retriever,
            memories=[SemanticMemory, EpisodicMemory, WorkingMemory],
        )
        self.react_node = ReactNode(
            llm=runtime_llm,
            system_prompt=str(react_prompts.get("system_prompt", "")),
            user_prompt=str(react_prompts.get("user_prompt", "{user_input}")),
            available_tools=tool_catalog_prompt,
            max_steps=6,
        )
        self.tool_execution_node = ToolExecutionNode(executor=self.tool_executor)
        self.reflect_node = ReflectNode(
            agent_name=self.agent_name,
            llm=self.reflect_llm or runtime_llm,
            system_prompt=str(reflect_prompts.get("system_prompt", "")),
            merge_feedback_into_observation=True,
            emit_memory_update=True,
            complete_route="complete",
            incomplete_route="incomplete",
        )
        self.response_node = ResponseNode(
            llm=self.response_llm,
            system_prompt=str(response_prompts.get("system_prompt", "")),
            user_prompt=str(response_prompts.get("user_prompt", "{observation}")),
            default_response="I need a bit more detail to help with that.",
        )
        self.memory_node = MemoryNode(
            memory_store=self.memory_store,
            memories=[WorkingMemory, EpisodicMemory, ReflectionMemory],
        )
        self.whatsapp_node = WhatsAppNode(interface=self.whatsapp, wait_for_reply=False)
        self.graph = self._build_graph()

    def run(self, user_input: str, session_id: str | None = None, *, trigger_type: str = "query") -> str:
        """Runs one MailMind turn through the compiled graph."""

        session_key = session_id or "mailmind-session"
        memory = self.session_store.load(session_key)
        trace = ExecutionTrace(agent_name=self.agent_name, session_id=session_key, user_input=user_input)
        with trace_turn(trace, sink=self.trace_sink):
            state = self.graph.invoke(
                {
                    "session_id": session_key,
                    "turn_id": str(uuid4()),
                    "trigger_type": trigger_type,
                    "user_input": user_input,
                    "memory": memory,
                    "memory_targets": [
                        {"type": "semantic", "limit": 5, "enabled": True},
                        {"type": "episodic", "limit": 5, "enabled": True},
                        {"type": "working", "limit": 6, "enabled": True},
                    ],
                    "observation": None,
                    "steps": 0,
                }
            )
            trace.finish(status="completed")
        return str(state.get("response", "I need a bit more detail to help with that."))

    def _build_graph(self) -> Any:
        graph = StateGraph(AgentState)
        graph.add_node("intent", self.intent_node.execute)
        graph.add_node("entry_router", self.entry_router.execute)
        graph.add_node("approval_router", self.approval_router.execute)
        graph.add_node("memory_retrieve", self.memory_retrieve_node.execute)
        graph.add_node("react", self.react_node.execute)
        graph.add_node("tool_execution", self.tool_execution_node.execute)
        graph.add_node("reflect", self.reflect_node.execute)
        graph.add_node("response", self.response_node.execute)
        graph.add_node("memory_write", self.memory_node.execute)
        graph.add_node("whatsapp_response", self.whatsapp_node.execute)

        graph.add_edge(START, "intent")
        graph.add_edge("intent", "entry_router")
        graph.add_conditional_edges(
            "entry_router",
            self.entry_router.route,
            {
                "poll": "memory_retrieve",
                "query": "memory_retrieve",
                "approval": "approval_router",
                "maintenance": "react",
            },
        )
        graph.add_conditional_edges(
            "approval_router",
            self.approval_router.route,
            {
                "approve_send": "memory_retrieve",
                "reject": "response",
                "redraft": "react",
                "more_context": "memory_retrieve",
            },
        )
        graph.add_edge("memory_retrieve", "react")
        graph.add_conditional_edges(
            "react",
            self.react_node.route,
            {
                "act": "tool_execution",
                "respond": "reflect",
                "end": END,
            },
        )
        graph.add_edge("tool_execution", "react")
        graph.add_conditional_edges(
            "reflect",
            self.reflect_node.route,
            {
                "incomplete": "react",
                "complete": "response",
            },
        )
        graph.add_edge("response", "memory_write")
        graph.add_edge("memory_write", "whatsapp_response")
        graph.add_edge("whatsapp_response", END)
        return graph.compile()

    def _build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(EmailSearchTool(repository=self.repository))
        registry.register(EmailSummaryTool(repository=self.repository))
        registry.register(DraftReplyTool(repository=self.repository))
        registry.register(MailMindSummaryTool(repository=self.repository))

        if self.source is not None:
            registry.register(
                GmailFetchTool(
                    source=self.source,
                    repository=self.repository,
                    classifier=self.classifier,
                )
            )
        if self.classifier is not None:
            registry.register(EmailClassifierTool(repository=self.repository, classifier=self.classifier))
        if self.sender is not None:
            registry.register(EmailSendTool(sender=self.sender, repository=self.repository))
        if self.notifier is not None:
            registry.register(
                NotificationTool(
                    notifier=self.notifier,
                    repository=self.repository,
                    approval_queue=self.approval_queue,
                )
            )
        if self.memory_retriever is not None:
            registry.register(MemorySearchTool(retriever=self.memory_retriever))
        if self.memory_store is not None:
            registry.register(MemoryWriteTool(store=self.memory_store))
        return registry


__all__ = ["MailMindAgent"]
