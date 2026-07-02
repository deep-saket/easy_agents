from __future__ import annotations

from agents.collection_agent.nodes.collection_entity_extract_node import CollectionEntityExtractNode
from agents.collection_agent.nodes.execution_path_intent_node import ExecutionPathIntentNode
from agents.collection_agent.nodes.pre_plan_intent_node import PrePlanIntentNode
from src.memory.types import WorkingMemory


class _EntityLLM:
    def __init__(self, entities: dict[str, str]) -> None:
        self.entities = entities
        self.calls = 0

    def generate_json(self, system_prompt: str, prompt: str) -> dict:
        del system_prompt
        self.calls += 1
        if "Required missing entity keys JSON" not in prompt:
            return {"entities": {}, "entity_descriptions": {}, "field_evidence": {}}
        return {
            "entities": dict(self.entities),
            "entity_descriptions": {key: "Extracted from current reply." for key in self.entities},
            "field_evidence": {},
        }


def _promise_memory() -> WorkingMemory:
    return WorkingMemory(
        session_id="required-entity-fallback",
        state={
            "payment_commitment_type": "PROMISE_TO_PAY",
            "promise_stage": "date_required",
            "conversation_mode": "promise_capture",
            "conversation_history": [
                {
                    "role": "agent",
                    "content": "What date works best for you to clear the full amount?",
                },
            ],
        },
    )


def test_expected_promise_date_is_extracted_before_asking_again() -> None:
    memory = _promise_memory()
    node = CollectionEntityExtractNode(llm=None)

    update = node.execute(
        {
            "memory": memory,
            "user_input": "the 4th would work for me",
        }
    )

    assert update["extracted_entities_turn"]["promised_date"] == "the 4th"
    assert memory.state["extracted_entities_turn"]["promised_date"] == "the 4th"
    assert update["entity_extraction_expected_fields"] == ["promised_date"]


def test_existing_entity_llm_receives_expected_promise_date_field() -> None:
    memory = _promise_memory()
    llm = _EntityLLM({"promised_date": "2026-07-04"})
    node = CollectionEntityExtractNode(llm=llm)

    update = node.execute(
        {
            "memory": memory,
            "user_input": "after my salary is credited",
        }
    )

    assert llm.calls == 1
    assert update["extracted_entities_turn"]["promised_date"] == "2026-07-04"
    assert memory.state["extracted_entities_turn"]["promised_date"] == "2026-07-04"


def test_promise_to_pay_date_captured_routes_to_tool_execution() -> None:
    memory = _promise_memory()
    memory.set_state(
        promise_stage="date_captured",
        promised_date="2026-07-04",
        promise_reference="",
    )

    pre_plan = PrePlanIntentNode(
        llm=None,
        allow_deterministic_fallback=False,
        system_prompt="",
        user_prompt="",
    )
    pre_update = pre_plan.execute(
        {
            "memory": memory,
            "user_input": "4th would work for me",
        }
    )
    assert pre_update["intent"]["intent"] == "decide"
    assert pre_update["llm_status"] == "skipped_by_pre_rule"

    execution = ExecutionPathIntentNode(
        llm=None,
        allow_deterministic_fallback=False,
        system_prompt="",
        user_prompt="",
    )
    exec_update = execution.execute(
        {
            "memory": memory,
            "user_input": "4th would work for me",
            "identity_verified": True,
            "verification_verified_fields": ["dob", "phone"],
            "verification_missing_fields": [],
        }
    )
    assert exec_update["intent"]["intent"] == "need_tool"
    assert exec_update["llm_status"] == "skipped_by_pre_rule"
