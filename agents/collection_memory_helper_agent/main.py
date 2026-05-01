"""CLI entrypoint for Collection Memory Helper Agent."""

from __future__ import annotations

import json
from pathlib import Path

from agents.collection_memory_helper_agent.agent import CollectionMemoryHelperAgent
from agents.collection_memory_helper_agent.repository import CollectionMemoryRepository


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    collection_runtime = root.parent / "collection_agent" / "runtime"
    agent = CollectionMemoryHelperAgent(repository=CollectionMemoryRepository(collection_runtime_dir=collection_runtime))
    sample = {
        "session_id": "demo-memory",
        "trigger": {"reason": "manual_demo"},
        "conversation_messages": [
            {"role": "user", "content": "I need lower EMI"},
            {"role": "agent", "content": "I can propose discount plan"},
            {"role": "user", "content": "Bye"},
        ],
        "conversation_state": {"active_case_id": "COLL-1001"},
    }
    print(json.dumps(agent.run(sample), indent=2, ensure_ascii=True))
