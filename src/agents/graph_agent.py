"""Created: 2026-04-01

Purpose: Implements the neutral graph-based shared agent runtime.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from src.agents.base_agent import BaseAgent
from src.agents.nodes import AgentState, MemoryRetrieveNode, ReflectNode, ResponseNode, SessionStoreProtocol, ToolExecutionNode
from src.agents.nodes.react_node import ReactNode
from src.memory.base import BaseMemoryStore
from src.tools.executor import ToolExecutor


class GraphAgent(BaseAgent):
    """Runs a node-composed agent graph.

    This is the shared runnable agent abstraction for the platform. It is
    intentionally neutral about reasoning style. The current default graph uses
    `PlannerNode`, `ToolExecutionNode`, `ReflectNode`, and `ResponseNode`, but
    future agents can compose different graphs from the same node vocabulary.

    The important architectural distinction is:

    - nodes contain reusable step logic
    - `GraphAgent` assembles and runs a graph of those nodes
    - concrete agents supply the planner, tools, memory, and storage bindings

    So the platform no longer treats "ReAct agent" as the main abstraction.
    ReAct is just one node pattern inside a general graph runner.

    This runtime does not require an LLM. If the supplied planner is purely
    rule-based, the graph still works because the planner remains the component
    responsible for producing decisions. The LLM is only one possible input to
    planning, not a hard dependency of the graph runner itself.
    """

    def __init__(
        self,
        *,
        llm: Any,
        planner: Any,
        tool_registry: Any,
        memory: Any,
        storage: Any,
        logger: Any,
        session_store: SessionStoreProtocol,
        tool_executor: ToolExecutor,
        memory_store: BaseMemoryStore | None = None,
        memory_retriever: Any | None = None,
        agent_name: str = "platform",
    ) -> None:
        """Initializes the graph agent and compiles its shared node graph.

        Args:
            llm: Optional LLM adapter available to the concrete agent.
            planner: Planner responsible for selecting the next step.
            tool_registry: Registry of tools the planner may use.
            memory: Optional working-memory dependency placeholder kept for
                compatibility with the base agent shape.
            storage: Durable operational store owned by the concrete agent.
            logger: Optional structured logger.
            session_store: Loader for session-scoped working memory objects.
            tool_executor: Runtime component that validates and executes tools.
            memory_store: Optional long-term memory write path.
            memory_retriever: Optional long-term memory read path.
            agent_name: Stable agent identifier used in reflection memory.
        """
        self.session_store = session_store
        self.tool_executor = tool_executor
        self.memory_store = memory_store
        self.memory_retriever = memory_retriever
        self.agent_name = agent_name
        self._graph: Any | None = None
        self._memory_retrieve_node: MemoryRetrieveNode | None = None
        self._planner_node: ReactNode | None = None
        self._tool_execution_node: ToolExecutionNode | None = None
        self._reflect_node: ReflectNode | None = None
        self._response_node: ResponseNode | None = None
        super().__init__(
            llm=llm,
            planner=planner,
            tool_registry=tool_registry,
            memory=memory,
            storage=storage,
            logger=logger,
            memory_store=memory_store,
            memory_retriever=memory_retriever,
        )
        self._memory_retrieve_node = MemoryRetrieveNode(
            tool_registry=self.tool_registry,
            llm=self.llm,
            memory_retriever=self.memory_retriever,
        )
        self._planner_node = ReactNode(planner=self.planner, llm=self.llm)
        self._tool_execution_node = ToolExecutionNode(executor=self.tool_executor, llm=self.llm)
        self._reflect_node = ReflectNode(memory_store=self.memory_store, agent_name=self.agent_name, llm=self.llm)
        self._response_node = ResponseNode(llm=self.llm)
        self._graph = self._build_graph()
        self.log_info(
            "Graph agent initialized",
            agent_name=self.agent_name,
            planner_type=type(self.planner).__name__,
            llm_enabled=self.llm is not None,
            tool_count=len(self.tool_registry.list_tools()) if hasattr(self.tool_registry, "list_tools") else "unknown",
        )

    def run(self, user_input: str, session_id: str | None = None) -> str:
        """Executes one user turn through the compiled node graph."""
        session_key = session_id or "default-session"
        self.log_info(
            "Starting graph agent turn",
            agent_name=self.agent_name,
            session_id=session_key,
            planner_type=type(self.planner).__name__,
            llm_enabled=self.llm is not None,
        )
        memory = self.session_store.load(session_key)
        memory.add_user_message(user_input)
        try:
            state = self._graph.invoke(
                {
                    "user_input": user_input,
                    "memory": memory,
                    "observation": None,
                    "steps": 0,
                }
            )
        except Exception:
            self.log_exception(
                "Graph agent turn failed",
                agent_name=self.agent_name,
                session_id=session_key,
            )
            raise
        response = state.get("response", "I’m not sure what to do next.")
        memory.add_agent_message(response)
        self.log_info(
            "Completed graph agent turn",
            agent_name=self.agent_name,
            session_id=session_key,
            steps=state.get("steps", 0),
            has_observation=state.get("observation") is not None,
            responded=bool(response),
        )
        return response

    def _build_graph(self) -> Any:
        """Builds the default shared node graph for an agent turn."""
        graph = StateGraph(AgentState)
        graph.add_node("retrieve_memory", self._memory_retrieve_node.execute)
        graph.add_node("plan", self._planner_node.execute)
        graph.add_node("act", self._act_node)
        graph.add_node("reflect", self._reflect_node.execute)
        graph.add_node("respond", self._respond_step)
        graph.add_edge(START, "retrieve_memory")
        graph.add_edge("retrieve_memory", "plan")
        graph.add_conditional_edges(
            "plan",
            self._planner_node.route,
            {"act": "act", "respond": "respond", "end": END},
        )
        graph.add_edge("act", "reflect")
        graph.add_edge("reflect", "plan")
        graph.add_edge("respond", END)
        return graph.compile()

    def _act_node(self, state: AgentState) -> AgentState:
        """Delegates tool execution to the shared tool node."""
        return self._tool_execution_node.execute(state)

    def _respond_step(self, state: AgentState) -> AgentState:
        """Delegates final response generation to the shared response node."""
        return self._response_node.execute(state)


__all__ = ["GraphAgent"]
