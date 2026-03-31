from __future__ import annotations

from dataclasses import dataclass

from llm.factory import LLMFactory
from mailmind.container import AppContainer


@dataclass(slots=True)
class MailMindAgentApp:
    container: AppContainer

    @classmethod
    def from_env(cls) -> "MailMindAgentApp":
        return cls(container=AppContainer.from_env())

    def run(self, user_input: str, session_id: str = "mailmind-default") -> str:
        return self.container.agent.run(user_input, session_id)

    @staticmethod
    def default_llm_example():
        return LLMFactory.build_default_local_llm()

