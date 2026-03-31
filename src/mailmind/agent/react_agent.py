from __future__ import annotations

from agents.react_agent import ReActAgent as SharedReActAgent
from memory.session_store import SessionStore


class ReActAgent(SharedReActAgent):
    def __init__(self, planner, executor, repository) -> None:
        SharedReActAgent.__init__(
            self,
            planner=planner,
            executor=executor,
            session_store=SessionStore(repository=repository),
        )
