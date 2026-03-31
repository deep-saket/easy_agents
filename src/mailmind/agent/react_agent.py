"""Created: 2026-03-31

Purpose: Implements the react agent module for the shared mailmind platform layer.
"""

from __future__ import annotations

from agents.react_agent import ReActAgent as SharedReActAgent
from memory.session_store import SessionStore


class ReActAgent(SharedReActAgent):
    def __init__(self, planner, executor, repository, memory_retriever=None) -> None:
        SharedReActAgent.__init__(
            self,
            planner=planner,
            executor=executor,
            session_store=SessionStore(repository=repository),
            memory_retriever=memory_retriever,
        )
