"""Created: 2026-04-09

Purpose: Exercises the layered memory system against the architecture in docs/architecture/memory-architecture.md.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from src.memory.layers import ColdMemoryLayer, HotMemoryLayer, WarmMemoryLayer
from src.memory.models import RetrievalContext, SleepingTask, utc_now
from src.memory.retrieval.retriever import LayeredMemoryRetriever
from src.memory.router import MemoryRouter
from src.memory.service import MemoryService
from src.memory.store import MemoryStore
from src.memory.tasks.sleeping_queue import SleepingTaskQueue
from src.memory.types import EpisodicMemory, SemanticMemory


def build_store(root: Path, name: str, *, scope: str, agent_id: str | None) -> MemoryStore:
    return MemoryStore(
        hot_layer=HotMemoryLayer(max_items=8),
        warm_layer=WarmMemoryLayer(root / f"{name}.duckdb"),
        cold_layer=ColdMemoryLayer(root / f"{name}.jsonl"),
        archive_after_days=30,
        default_scope=scope,
        agent_id=agent_id,
    )


def test_memory_store_persists_json_records_in_warm_and_cold_layers(tmp_path: Path) -> None:
    store = build_store(tmp_path, "local", scope="agent_local", agent_id="mailmind")

    current = SemanticMemory(content={"fact": "prefers structured memory"}, metadata={"tags": ["json"]}).store_warm(store)
    archived = SemanticMemory(
        content={"fact": "old cold memory"},
        created_at=utc_now() - timedelta(days=45),
    ).store_warm(store)

    archived_count = store.archive_old()
    row = store.warm_layer._backend._conn.execute(  # type: ignore[attr-defined]
        "SELECT agent_id, scope, memory_type, content_json, metadata_json FROM memory_records WHERE id = ?",
        [current.id],
    ).fetchone()
    cold_payload = store.cold_layer.file_path.read_text(encoding="utf-8")

    assert archived_count == 1
    assert row[0] == "mailmind"
    assert row[1] == "agent_local"
    assert row[2] == "semantic"
    assert '"fact": "prefers structured memory"' in row[3]
    assert '"agent": "mailmind"' in row[4]
    assert archived.id in cold_payload
    assert '"layer":"cold"' in cold_payload


def test_layered_retrieval_rehydrates_archived_records(tmp_path: Path) -> None:
    store = build_store(tmp_path, "local", scope="agent_local", agent_id="mailmind")
    archived = SemanticMemory(
        content={"fact": "old archived preference"},
        created_at=utc_now() - timedelta(days=45),
    ).store_warm(store)
    store.archive_old()

    retrieved = store.get(archived.id)

    assert retrieved is not None
    assert retrieved.layer == "warm"
    assert store.hot_layer.get(archived.id) is not None
    assert store.warm_layer.get(archived.id) is not None


def test_memory_service_escalates_from_local_to_global_when_context_requires_it(tmp_path: Path) -> None:
    local_store = build_store(tmp_path, "local", scope="agent_local", agent_id="mailmind")
    global_store = build_store(tmp_path, "global", scope="global", agent_id=None)
    service = MemoryService(
        local_store=local_store,
        global_store=global_store,
        router=MemoryRouter(
            local_retriever=LayeredMemoryRetriever(local_store),
            global_retriever=LayeredMemoryRetriever(global_store),
        ),
    )
    global_record = service.add_global(SemanticMemory(content={"fact": "endpoint auth uses api keys"}, scope="global"))

    results = service.retrieve(
        "api keys",
        filters={"type": "semantic"},
        limit=5,
        context=RetrievalContext(agent_id="mailmind", step_count=4, confidence=0.4, allow_global=True),
    )

    assert [record.id for record in results] == [global_record.id]
    assert results[0].scope == "global"


def test_episodic_memory_is_cached_hot_and_persisted_warm(tmp_path: Path) -> None:
    store = build_store(tmp_path, "local", scope="agent_local", agent_id="mailmind")

    stored = EpisodicMemory(content={"event": "classified a DeepMind email"}).store_hot(store)

    assert stored.layer == "warm"
    assert store.hot_layer.get(stored.id) is not None
    assert store.warm_layer.get(stored.id) is not None


def test_sleeping_task_queue_orders_by_priority_and_pops_head(tmp_path: Path) -> None:
    queue = SleepingTaskQueue(tmp_path / "sleeping.jsonl")
    queue.enqueue(SleepingTask(task_type="reindex", payload={"scope": "agent_local"}, priority=1))
    queue.enqueue(SleepingTask(task_type="summarize", payload={"date": "2026-04-09"}, priority=5))

    listed = queue.list_tasks()
    popped = queue.pop_next()
    remaining = queue.list_tasks()

    assert [(task.task_type, task.priority) for task in listed] == [("summarize", 5), ("reindex", 1)]
    assert popped is not None
    assert popped.task_type == "summarize"
    assert [(task.task_type, task.priority) for task in remaining] == [("reindex", 1)]


def test_memory_store_supports_created_before_and_after_filters(tmp_path: Path) -> None:
    store = build_store(tmp_path, "local", scope="agent_local", agent_id="mailmind")
    cutoff = utc_now() - timedelta(days=1)
    older = SemanticMemory(
        content={"fact": "older memory"},
        created_at=cutoff - timedelta(hours=2),
        agent_id="mailmind",
    ).store_warm(store)
    newer = SemanticMemory(
        content={"fact": "newer memory"},
        created_at=cutoff + timedelta(hours=2),
        agent_id="mailmind",
    ).store_warm(store)

    before_results = store.search("", filters={"created_before": cutoff.isoformat()}, limit=10)
    after_results = store.search("", filters={"created_after": cutoff.isoformat()}, limit=10)

    assert [record.id for record in before_results] == [older.id]
    assert [record.id for record in after_results] == [newer.id]
