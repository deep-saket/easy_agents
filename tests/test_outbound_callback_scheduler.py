from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.collection_agent.services.outbound_callback_queue import (
    OutboundCallbackQueue,
    resolve_callback_datetime,
)
from agents.collection_agent.nodes.collection_react_node import CollectionReactNode
from agents.collection_agent.nodes.plan_proposal_state_node import PlanProposalStateNode
from agents.collection_agent.nodes.plan_proposal_directive_node import PlanProposalDirectiveNode
from agents.collection_agent.nodes.plan_proposal_graph_node import PlanProposalGraphNode
from agents.collection_agent.tools.data_store import CollectionDataStore
from agents.collection_agent.tools.outbound_callback_cancel_tool import OutboundCallbackCancelTool
from agents.collection_agent.tools.outbound_callback_schedule_tool import OutboundCallbackScheduleTool
from agents.collection_agent.tools.schemas import (
    OutboundCallbackCancelInput,
    OutboundCallbackScheduleInput,
)
from src.memory.types import WorkingMemory
from src.nodes.tool_execution_node import ToolExecutionNode
from src.tools.executor import ToolExecutor
from src.tools.registry import ToolRegistry


def test_resolve_callback_time_to_absolute_timestamp() -> None:
    now = datetime(2026, 6, 11, 10, 0, tzinfo=UTC)
    resolved = resolve_callback_datetime(
        "at 5:30 PM today",
        timezone_name="Asia/Kolkata",
        now=now,
    )
    assert resolved.isoformat() == "2026-06-11T17:30:00+05:30"


def test_queue_dispatches_due_callback_and_records_attempt() -> None:
    with TemporaryDirectory() as raw_dir:
        queue = OutboundCallbackQueue(
            runtime_dir=Path(raw_dir),
            dispatch=lambda job: {"provider_reference": f"provider-{job['job_id']}"},
        )
        now = datetime(2026, 6, 11, 10, 0, tzinfo=UTC)
        job = queue.schedule(
            case_id="COLL-1002",
            customer_id="CUST-2002",
            session_id="session-1",
            callback_time="at 3:31 PM today",
            timezone_name="Asia/Kolkata",
            phone="+919900001002",
            max_retries=3,
            now=now,
        )
        processed = queue.process_due(now=now + timedelta(minutes=1))

        assert job["status"] == "scheduled"
        assert processed[0]["status"] == "dispatched"
        assert queue._read_rows(queue.attempts_path)[0]["status"] == "completed"


def test_queue_retries_then_fails_provider_errors() -> None:
    with TemporaryDirectory() as raw_dir:
        def fail_dispatch(_: dict) -> dict:
            raise RuntimeError("provider unavailable")

        queue = OutboundCallbackQueue(
            runtime_dir=Path(raw_dir),
            dispatch=fail_dispatch,
            expiry_grace_minutes=120,
        )
        now = datetime(2026, 6, 11, 10, 0, tzinfo=UTC)
        job = queue.schedule(
            case_id="COLL-1002",
            customer_id="CUST-2002",
            session_id="session-1",
            callback_time="at 3:31 PM today",
            timezone_name="Asia/Kolkata",
            phone="+919900001002",
            max_retries=1,
            now=now,
        )
        first = queue.process_due(now=now + timedelta(minutes=1))[0]
        second = queue.process_due(now=datetime.fromisoformat(first["next_attempt_at"]))[0]

        assert job["status"] == "scheduled"
        assert first["status"] == "retrying"
        assert second["status"] == "failed"
        assert second["retry_count"] == 2


def test_queue_supports_cancellation_and_expiry() -> None:
    with TemporaryDirectory() as raw_dir:
        queue = OutboundCallbackQueue(runtime_dir=Path(raw_dir), dispatch=lambda _: {})
        now = datetime(2026, 6, 11, 10, 0, tzinfo=UTC)
        job = queue.schedule(
            case_id="COLL-1002",
            customer_id="CUST-2002",
            session_id="session-1",
            callback_time="at 3:31 PM today",
            timezone_name="Asia/Kolkata",
            phone="+919900001002",
            max_retries=3,
            now=now,
        )
        cancelled = queue.cancel(job_id=job["job_id"], reason="customer_requested", now=now)
        expired = queue.schedule(
            case_id="COLL-1003",
            customer_id="CUST-2003",
            session_id="session-2",
            callback_time="at 1 PM today",
            timezone_name="Asia/Kolkata",
            phone="+919900001003",
            max_retries=3,
            now=now,
        )

        assert cancelled == [job["job_id"]]
        assert expired["status"] == "expired"


def test_schedule_and_cancel_tools_use_durable_queue() -> None:
    with TemporaryDirectory() as raw_dir:
        root = Path(raw_dir)
        (root / "data").mkdir()
        (root / "data" / "customers.json").write_text(
            '[{"customer_id":"CUST-2002","phone":"+919900001002"}]\n',
            encoding="utf-8",
        )
        store = CollectionDataStore(base_dir=root)
        queue = OutboundCallbackQueue(runtime_dir=store.runtime_dir, dispatch=lambda _: {})
        schedule_tool = OutboundCallbackScheduleTool(store=store, queue=queue)
        cancel_tool = OutboundCallbackCancelTool(queue=queue)

        scheduled = schedule_tool.execute(
            OutboundCallbackScheduleInput(
                case_id="COLL-1002",
                customer_id="CUST-2002",
                session_id="session-1",
                callback_time="tomorrow morning",
            )
        )
        cancelled = cancel_tool.execute(
            OutboundCallbackCancelInput(job_id=scheduled.job_id, reason="customer_requested")
        )

        assert scheduled.status == "scheduled"
        assert cancelled.status == "cancelled"
        assert cancelled.cancelled_job_ids == [scheduled.job_id]


def test_queue_recovers_from_corrupt_runtime_json() -> None:
    with TemporaryDirectory() as raw_dir:
        root = Path(raw_dir)
        queue = OutboundCallbackQueue(runtime_dir=root, dispatch=lambda _: {})
        queue.queue_path.write_bytes(b"\x00\x00\x00\x00")

        job = queue.schedule(
            case_id="COLL-1002",
            customer_id="CUST-2002",
            session_id="session-1",
            callback_time="tomorrow morning",
            timezone_name="Asia/Kolkata",
            phone="+919900001002",
            max_retries=3,
            now=datetime(2026, 6, 11, 10, 0, tzinfo=UTC),
        )

        assert job["status"] == "scheduled"
        assert queue._read_rows(queue.queue_path)[0]["job_id"] == job["job_id"]


def test_wrong_party_callback_turn_selects_scheduler_tool() -> None:
    with TemporaryDirectory() as raw_dir:
        root = Path(raw_dir)
        (root / "data").mkdir()
        (root / "data" / "customers.json").write_text(
            '[{"customer_id":"CUST-2002","phone":"+919900001002"}]\n',
            encoding="utf-8",
        )
        store = CollectionDataStore(base_dir=root)
        queue = OutboundCallbackQueue(runtime_dir=store.runtime_dir, dispatch=lambda _: {})
        registry = ToolRegistry()
        registry.register(OutboundCallbackScheduleTool(store=store, queue=queue))
        registry.register(OutboundCallbackCancelTool(queue=queue))
        node = CollectionReactNode(
            llm=None,
            system_prompt="",
            user_prompt="{user_input}",
            available_tools="",
            tool_registry=registry,
        )
        memory = WorkingMemory(
            session_id="session-1",
            state={
                "active_case_id": "COLL-1002",
                "active_user_id": "CUST-2002",
                "right_party_status": "wrong_party",
                "wrong_party_callback_stage": "awaiting_callback",
                "timezone": "Asia/Kolkata",
            },
        )

        update = node.execute(
            {
                "session_id": "session-1",
                "case_id": "COLL-1002",
                "user_id": "CUST-2002",
                "user_input": "he is not here, please try at 5:30pm tomorrow",
                "memory": memory,
                "observations": [],
                "steps": 0,
            }
        )

        assert update["decision"].tool_call.tool_name == "outbound_callback_schedule"
        assert update["decision"].tool_call.arguments["callback_time"] == "at 5:30 PM tomorrow"

        tool_update = ToolExecutionNode(executor=ToolExecutor(registry=registry)).execute(
            {
                **update,
                "memory": memory,
                "observations": [],
            }
        )
        completion_update = node.execute(
            {
                "session_id": "session-1",
                "case_id": "COLL-1002",
                "user_id": "CUST-2002",
                "user_input": "he is not here, please try at 5:30pm tomorrow",
                "memory": memory,
                "steps": update["steps"],
                **tool_update,
            }
        )

        assert completion_update["decision"].done is True
        assert memory.state["outbound_callback_job_id"]
        assert memory.state["outbound_callback_status"] == "scheduled"


def test_scheduled_callback_tool_result_leads_to_confirmation_directive() -> None:
    memory = WorkingMemory(
        session_id="session-1",
        state={
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_customer_name": "Rohan Gupta",
            "identity_verified": False,
            "right_party_status": "wrong_party",
            "wrong_party_callback_stage": "awaiting_callback",
        },
    )
    node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)

    update = node.execute(
        {
            "user_input": "try at 11AM today",
            "memory": memory,
            "observations": [
                {
                    "tool_phase": {
                        "tool_name": "outbound_callback_schedule",
                        "input": {
                            "case_id": "COLL-1002",
                            "customer_id": "CUST-2002",
                            "session_id": "session-1",
                            "callback_time": "at 11 AM today",
                            "timezone": "Asia/Kolkata",
                            "phone": None,
                            "max_retries": 3,
                        },
                        "output": {
                            "job_id": "CALL-123",
                            "case_id": "COLL-1002",
                            "customer_id": "CUST-2002",
                            "session_id": "session-1",
                            "scheduled_for": "2026-06-24T11:00:00+05:30",
                            "timezone": "Asia/Kolkata",
                            "phone": "+919900001002",
                            "status": "scheduled",
                            "retry_count": 0,
                        },
                    }
                }
            ],
            "steps": 1,
        }
    )

    directive = update["plan_proposal"]["response_directive"]
    assert directive["conversation_objective"] == "wrong_party_callback_confirmation"
    assert memory.state["wrong_party_callback_stage"] == "completed"
    assert memory.state["wrong_party_callback_time"] == "at 11 AM today"


def test_verified_customer_callback_without_time_asks_for_callback_time() -> None:
    memory = WorkingMemory(
        session_id="session-customer-callback",
        state={
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_customer_name": "Rohan Gupta",
            "identity_verified": True,
            "right_party_status": "right_party",
        },
    )
    node = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False)

    update = node.execute(
        {
            "user_input": "I'm in a meeting, can you call later?",
            "memory": memory,
            "observations": [],
            "steps": 0,
        }
    )

    directive = update["plan_proposal"]["response_directive"]
    assert directive["conversation_objective"] == "customer_callback_request"
    assert memory.state["customer_callback_stage"] == "awaiting_callback"
    assert not memory.state.get("customer_callback_time")


def test_pre_verification_right_party_callback_uses_customer_callback_node() -> None:
    memory = WorkingMemory(
        session_id="session-customer-callback-preverify",
        state={
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "active_customer_name": "Rohan Gupta",
            "identity_verified": False,
            "right_party_status": "right_party",
        },
    )
    directive_update = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False).execute(
        {
            "user_input": "Yes, but I'm in a meeting right now.",
            "memory": memory,
            "observations": [],
            "steps": 0,
        }
    )
    assert directive_update["plan_proposal"]["response_directive"]["conversation_objective"] == "customer_callback_request"
    assert memory.state["customer_callback_stage"] == "awaiting_callback"

    graph_update = PlanProposalGraphNode(llm=None, strict_llm_mode=False).execute(
        {
            "user_input": "Yes, but I'm in a meeting right now.",
            "memory": memory,
            "plan_proposal": directive_update["plan_proposal"],
        }
    )
    assert graph_update["conversation_plan"]["current_node_id"] == "customer_callback"
    markers = graph_update["conversation_plan"].get("step_markers", {})
    assert markers["verify_identity"]["state"] == "skipped"
    assert markers["purpose_disclosure"]["state"] == "pending"
    assert markers["customer_callback"]["state"] == "pending"


def test_plan_state_sets_customer_callback_before_graph_runs() -> None:
    memory = WorkingMemory(
        session_id="session-customer-callback-state",
        state={
            "active_case_id": "COLL-1003",
            "active_user_id": "CUST-2003",
            "active_customer_name": "Neha Verma",
            "identity_verified": False,
            "right_party_status": "awaiting_confirmation",
            "conversation_mode": "verification",
            "response_mode": "compliance",
        },
    )

    state_update = PlanProposalStateNode(llm=None, strict_llm_mode=False).execute(
        {
            "user_input": "Yes, but I'm in a meeting right now",
            "memory": memory,
            "observations": [],
        }
    )
    assert state_update["plan_prepared_memory_state"]["customer_callback_stage"] == "awaiting_callback"
    assert memory.state["customer_callback_stage"] == "awaiting_callback"

    graph_update = PlanProposalGraphNode(llm=None, strict_llm_mode=False).execute(
        {
            "user_input": "Yes, but I'm in a meeting right now",
            "memory": memory,
            **state_update,
        }
    )
    assert graph_update["conversation_plan"]["current_node_id"] == "customer_callback"


def test_verified_customer_callback_reuses_outbound_scheduler_tool() -> None:
    with TemporaryDirectory() as raw_dir:
        root = Path(raw_dir)
        (root / "data").mkdir()
        (root / "data" / "customers.json").write_text(
            '[{"customer_id":"CUST-2002","phone":"+919900001002"}]\n',
            encoding="utf-8",
        )
        store = CollectionDataStore(base_dir=root)
        queue = OutboundCallbackQueue(runtime_dir=store.runtime_dir, dispatch=lambda _: {})
        registry = ToolRegistry()
        registry.register(OutboundCallbackScheduleTool(store=store, queue=queue))
        react = CollectionReactNode(
            llm=None,
            system_prompt="",
            user_prompt="{user_input}",
            available_tools="",
            tool_registry=registry,
        )
        memory = WorkingMemory(
            session_id="session-customer-callback",
            state={
                "active_case_id": "COLL-1002",
                "active_user_id": "CUST-2002",
                "active_customer_name": "Rohan Gupta",
                "identity_verified": False,
                "right_party_status": "right_party",
                "customer_callback_stage": "awaiting_callback",
                "timezone": "Asia/Kolkata",
            },
        )

        state = {
            "session_id": "session-customer-callback",
            "case_id": "COLL-1002",
            "user_id": "CUST-2002",
            "user_input": "Call me around 7 PM today.",
            "memory": memory,
            "observations": [],
            "steps": 0,
        }
        update = react.execute(state)

        assert update["decision"].tool_call.tool_name == "outbound_callback_schedule"
        assert update["decision"].tool_call.arguments["callback_time"] == "at 7 PM today"

        tool_update = ToolExecutionNode(executor=ToolExecutor(registry=registry)).execute(
            {
                **state,
                **update,
                "observations": [],
            }
        )
        completion_update = react.execute(
            {
                **state,
                "steps": update["steps"],
                **tool_update,
            }
        )

        assert completion_update["decision"].done is True
        assert memory.state["customer_callback_stage"] == "completed"
        assert memory.state["customer_callback_time"] == "at 7 PM today"
        assert memory.state["outbound_callback_status"] == "scheduled"
        assert queue._read_rows(queue.queue_path)[0]["job_id"] == memory.state["outbound_callback_job_id"]

        directive = PlanProposalDirectiveNode(llm=None, strict_llm_mode=False).execute(
            {
                **state,
                "steps": update["steps"],
                **tool_update,
            }
        )["plan_proposal"]["response_directive"]
        assert directive["conversation_objective"] == "customer_callback_confirmation"


def test_wrong_party_callback_cancellation_selects_cancel_tool() -> None:
    node = CollectionReactNode(
        llm=None,
        system_prompt="",
        user_prompt="{user_input}",
        available_tools="",
        tool_registry=None,
    )
    memory = WorkingMemory(
        session_id="session-1",
        state={
            "active_case_id": "COLL-1002",
            "active_user_id": "CUST-2002",
            "right_party_status": "wrong_party",
            "wrong_party_callback_stage": "completed",
            "outbound_callback_job_id": "CALL-123",
        },
    )

    update = node.execute(
        {
            "session_id": "session-1",
            "case_id": "COLL-1002",
            "user_id": "CUST-2002",
            "user_input": "Please cancel the callback",
            "memory": memory,
            "observations": [],
            "steps": 0,
        }
    )

    assert update["decision"].tool_call.tool_name == "outbound_callback_cancel"
    assert update["decision"].tool_call.arguments["job_id"] == "CALL-123"
