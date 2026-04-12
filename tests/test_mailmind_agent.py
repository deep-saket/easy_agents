"""Created: 2026-04-11

Purpose: Smoke-tests the MailMind graph agent against the shared node runtime.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from agents.mailmind import MailMindAgent
from src.interfaces.whatsapp import MockWhatsAppInterface
from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.store import MemoryStore
from src.memory.types import ReflectionMemory
from src.schemas.domain import ActionType, Category, ClassificationResult, EmailMessage, SuggestedAction
from src.storage.duckdb_store import DuckDBMessageRepository


class SequencedLLM:
    """Returns fixed outputs in order and records prompts for inspection."""

    model_name = "sequenced-llm"

    def __init__(self, *outputs: str) -> None:
        self._outputs = deque(outputs)
        self.calls: list[tuple[str, str]] = []

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if not self._outputs:
            raise AssertionError("SequencedLLM ran out of outputs.")
        return self._outputs.popleft()


def build_repository(tmp_path: Path) -> DuckDBMessageRepository:
    repository = DuckDBMessageRepository(tmp_path / "mailmind_agent.db")
    repository.init_db()
    return repository


def build_memory_store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=WarmMemoryLayer(tmp_path / "mailmind_memory.db"),
        cold_layer=ColdMemoryLayer(tmp_path / "mailmind_memory.jsonl"),
        archive_after_days=30,
        default_scope="agent_local",
        agent_id="mailmind",
    )


def seed_message(repository: DuckDBMessageRepository) -> str:
    message = repository.save_message(
        EmailMessage(
            source_id="gmail-1",
            from_email="research@example.com",
            subject="Interview follow-up",
            body_text="Can we schedule a follow-up conversation next week?",
            received_at=datetime.now(timezone.utc),
        )
    )
    repository.save_classification(
        ClassificationResult(
            message_id=message.id,
            priority_score=0.93,
            impact_score=0.91,
            category=Category.TIME_SENSITIVE_PROFESSIONAL,
            requires_action=True,
            action_type=ActionType.REPLY,
            confidence=0.97,
            reason_codes=["follow_up"],
            reasoning="Time-sensitive email that likely needs a reply.",
            suggested_action=SuggestedAction.NOTIFY_AND_DRAFT,
            summary="Needs a reply about scheduling a follow-up conversation.",
        )
    )
    return message.id


def test_mailmind_agent_runs_tool_then_reflects_then_sends_whatsapp(tmp_path: Path) -> None:
    repository = build_repository(tmp_path)
    memory_store = build_memory_store(tmp_path)
    message_id = seed_message(repository)
    whatsapp = MockWhatsAppInterface()
    intent_llm = SequencedLLM('{"intent":"query_mail","confidence":0.98,"reason":"User asked about inbox status."}')
    react_llm = SequencedLLM(
        f'{{"thought":"Summarize the referenced email first.","tool_name":"email_summary","arguments":{{"message_ids":["{message_id}"],"max_items":1}}}}',
        '{"thought":"The summary is enough.","respond_directly":true,"response_text":"You have one urgent follow-up email that needs a reply.","done":true}',
    )
    reflect_llm = SequencedLLM('{"reason":"The tool output is sufficient to answer the user.","is_complete":true}')
    agent = MailMindAgent(
        llm=react_llm,
        intent_llm=intent_llm,
        reflect_llm=reflect_llm,
        repository=repository,
        whatsapp=whatsapp,
        memory_store=memory_store,
    )

    response = agent.run("Summarize my most urgent email.", session_id="whatsapp:+15550001111")

    assert response == "You have one urgent follow-up email that needs a reply."
    assert whatsapp.outbound_messages == [("whatsapp:+15550001111", response)]
    assert repository.list_conversation_messages("whatsapp:+15550001111")[-2:]
    assert repository.list_conversation_messages("whatsapp:+15550001111")[-1].content == response
    reflection_hits = ReflectionMemory.search(memory_store, "", agent_id="mailmind")
    assert reflection_hits
    assert "sufficient" in str(reflection_hits[0].content).lower()


def test_mailmind_agent_loops_back_to_react_when_reflection_is_incomplete(tmp_path: Path) -> None:
    repository = build_repository(tmp_path)
    message_id = seed_message(repository)
    whatsapp = MockWhatsAppInterface()
    intent_llm = SequencedLLM('{"intent":"query_mail","confidence":0.9,"reason":"Normal user query."}')
    react_llm = SequencedLLM(
        '{"thought":"I can probably answer now.","respond_directly":true,"response_text":"I have a tentative answer.","done":true}',
        f'{{"thought":"Need the actual email summary.","tool_name":"email_summary","arguments":{{"message_ids":["{message_id}"],"max_items":1}}}}',
        '{"thought":"Now the answer is grounded.","respond_directly":true,"response_text":"You have one urgent follow-up email waiting for a reply.","done":true}',
    )
    reflect_llm = SequencedLLM(
        '{"reason":"No grounded email detail yet. Use a tool.","is_complete":false}',
        '{"reason":"The answer is now complete.","is_complete":true}',
    )
    agent = MailMindAgent(
        llm=react_llm,
        intent_llm=intent_llm,
        reflect_llm=reflect_llm,
        repository=repository,
        whatsapp=whatsapp,
    )

    response = agent.run("What needs my attention right now?", session_id="whatsapp:+15550002222")

    assert response == "You have one urgent follow-up email waiting for a reply."
    assert whatsapp.outbound_messages == [("whatsapp:+15550002222", response)]
    assert len(react_llm.calls) == 3
    assert "reflection_feedback" in react_llm.calls[1][1]
