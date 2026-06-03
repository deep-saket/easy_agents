from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agents.collection_agent.conversation_manager.ConversationManagerAgent import ConversationManagerAgent
from agents.collection_agent.conversation_manager.ConversationManagerConfig import ConversationManagerConfig
from agents.collection_agent.conversation_manager.runtime import ConversationManagedRuntime


class _FakeCollectionRuntime:
    def __init__(self) -> None:
        self.started = False

    def start_conversation(self, request):
        self.started = True
        return {"turn": {"final_response": "hello", "final_target": "customer"}}

    def reset_conversation(self, request):
        return {"status": "reset", "session_id": request.session_id}

    def run_turn(self, request, event_callback=None):
        return {
            "session_id": request.session_id,
            "final_response": "reply",
            "final_target": "customer",
            "hops": [],
        }

    def session_state(self, session_id):
        return {"session_id": session_id}

    def list_demo_users(self):
        return [{"user_code": "user_a", "customer": {"name": "Aditi"}, "case": {"case_id": "COLL-1"}}]

    def conversation_messages(self, session_id, *, limit=120):
        return [{"role": "agent", "content": "x"}]

    def latest_trace_for_session(self, session_id):
        return {"session_id": session_id}

    def voice_status(self):
        return {"active": False}

    def stop_voice_call(self, *, force=False):
        return {"active": False}


def test_runtime_wraps_downstream_without_touching_collection_sources(tmp_path: Path) -> None:
    config = ConversationManagerConfig.default(
        base_dir=Path("/Users/saketm10/Projects/openclaw_agents/agents/collection_agent/conversation_manager")
    )
    config.runtime_dir = tmp_path / "runtime"
    runtime = ConversationManagedRuntime(
        base_dir=tmp_path,
        collection_base_dir=tmp_path / "collection_agent",
        downstream_runtime=_FakeCollectionRuntime(),
        manager=None,  # type: ignore[arg-type]
        voice_manager=None,  # type: ignore[arg-type]
    )
    runtime.manager = ConversationManagerAgent(config=config, downstream_runtime=runtime.downstream_runtime)
    result = runtime.run_turn(SimpleNamespace(message="hello", session_id="abc"))
    assert result["final_response"] == "reply"
    assert "conversation_manager" in result
