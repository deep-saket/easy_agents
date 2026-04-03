"""Created: 2026-04-01

Purpose: Binds the shared graph agent runtime to MailMind dependencies.
"""

from __future__ import annotations

from src.agents.graph_agent import GraphAgent as SharedGraphAgent
from src.memory.session_store import SessionStore


class MailMindGraphAgent(SharedGraphAgent):
    """Specializes the shared graph agent with MailMind session storage."""

    def __init__(self, planner, executor, repository, memory_retriever=None, memory_store=None, trace_sink=None) -> None:
        SharedGraphAgent.__init__(
            self,
            llm=None,
            planner=planner,
            tool_registry=executor.registry,
            memory=None,
            storage=repository,
            logger=None,
            session_store=SessionStore(repository=repository),
            tool_executor=executor,
            memory_store=memory_store,
            memory_retriever=memory_retriever,
            agent_name="mailmind",
            trace_sink=trace_sink,
        )
