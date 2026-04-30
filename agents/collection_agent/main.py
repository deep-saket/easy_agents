"""CLI entrypoint for Collection Agent demo."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import yaml

from agents.collection_agent.agent import CollectionAgent
from agents.discount_planning_agent.agent import DiscountPlanningAgent
from agents.collection_agent.repository import CollectionRepository
from agents.collection_agent.tools.data_store import CollectionDataStore
from src.llm import LLMFactory
from src.platform_logging.tracing import JSONLTraceSink, StdoutJSONTraceSink, TraceSink

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yml")


class MultiTraceSink:
    """Fan-out sink that emits events to multiple sinks."""

    def __init__(self, sinks: list[TraceSink]) -> None:
        self._sinks = sinks

    def emit(self, event: dict[str, Any]) -> None:
        for sink in self._sinks:
            sink.emit(event)


def load_collection_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config file {config_path} must contain a mapping at the top level.")
    return payload


def build_parser(defaults: dict[str, Any]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Collection Agent demo.")
    parser.add_argument("message", nargs="?", help="One turn input.")
    parser.add_argument("--session-id", default=str(defaults.get("session_id", "collection-showcase")), help="Session id")
    parser.add_argument("--base-dir", default=str(defaults.get("base_dir", Path(__file__).resolve().parent)), help="Agent base directory")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--config", default=str(defaults.get("config_path", DEFAULT_CONFIG_PATH)), help="Path to collection config")
    parser.add_argument("--openai-api-key", default=None, help="Override OPENAI_API_KEY for this run")
    parser.add_argument("--disable-llm", action="store_true", help="Disable LLM usage and run deterministic planner fallback")
    parser.add_argument("--trace-jsonl", default=None, help="Optional JSONL event trace output path")
    parser.add_argument("--trace-stdout-json", action="store_true", help="Emit real-time trace events to stdout as JSON lines")
    parser.add_argument("--trace-readable", action="store_true", help="Print readable node/tool traversal summary per turn")
    parser.add_argument(
        "--agent-hop-soft-cap",
        type=int,
        default=int(defaults.get("agent_hop_soft_cap", 10)),
        help="Soft max internal agent hops per user turn (default: 10)",
    )
    parser.add_argument(
        "--agent-hop-hard-cap",
        type=int,
        default=int(defaults.get("agent_hop_hard_cap", 50)),
        help="Hard safety cap for internal agent hops per user turn (default: 50)",
    )
    return parser


def build_llm(config: dict[str, Any], cli_openai_api_key: str | None = None, force_disable: bool = False) -> Any | None:
    llm_cfg = dict(config.get("llm", {})) if isinstance(config.get("llm"), dict) else {}
    if force_disable:
        return None
    enabled = bool(llm_cfg.get("enabled", True))
    if not enabled:
        return None

    provider = str(llm_cfg.get("provider", "openai")).strip().lower()
    model_name = str(llm_cfg.get("model_name", "gpt-4o-mini"))
    max_new_tokens = llm_cfg.get("max_new_tokens")
    temperature = llm_cfg.get("temperature")

    if provider != "openai":
        raise ValueError(f"Collection Agent currently supports provider=openai for this runtime, got: {provider}")

    api_key = cli_openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for llm.provider=openai. Pass --openai-api-key or export OPENAI_API_KEY.")

    return LLMFactory.build_openai_llm(
        model_name=model_name,
        api_key=api_key,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
    )


def build_trace_sink(args: argparse.Namespace, base_dir: Path, config: dict[str, Any]) -> TraceSink | None:
    sinks: list[TraceSink] = []

    if args.trace_stdout_json:
        sinks.append(StdoutJSONTraceSink())

    trace_cfg = dict(config.get("tracing", {})) if isinstance(config.get("tracing"), dict) else {}
    jsonl_path = args.trace_jsonl or trace_cfg.get("jsonl_path")
    if jsonl_path:
        path = Path(str(jsonl_path))
        if not path.is_absolute():
            path = base_dir / path
        sinks.append(JSONLTraceSink(path))

    if not sinks:
        return None
    if len(sinks) == 1:
        return sinks[0]
    return MultiTraceSink(sinks)


def format_trace_summary(agent: CollectionAgent) -> str:
    trace = agent.last_trace
    if trace is None:
        return "[trace] no trace captured"
    nodes = " -> ".join(node.node_name for node in trace.node_traces)
    tools = " -> ".join(call.tool_name for call in trace.tool_calls) if trace.tool_calls else "(none)"
    payload = {
        "trace_id": trace.trace_id,
        "status": trace.status,
        "node_order": [node.node_name for node in trace.node_traces],
        "tool_order": [call.tool_name for call in trace.tool_calls],
        "node_count": len(trace.node_traces),
        "tool_call_count": len(trace.tool_calls),
    }
    return (
        "[trace-summary]\n"
        f"nodes: {nodes}\n"
        f"tools: {tools}\n"
        f"json: {json.dumps(payload, ensure_ascii=True)}"
    )


def _route_internal_turn(
    *,
    collection_agent: CollectionAgent,
    discount_agent: DiscountPlanningAgent,
    session_id: str,
    initial_input: str,
    soft_cap: int,
    hard_cap: int,
    trace_readable: bool,
) -> str:
    memory = collection_agent.session_store.load(session_id)
    current_input = initial_input

    for hop in range(1, hard_cap + 1):
        state = collection_agent.run_turn(current_input, session_id=session_id)
        response = str(state.get("response", "No response generated."))
        target = str(state.get("response_target", "customer")).strip().lower()

        if trace_readable:
            print(f"[hop {hop}] target={target}")
            print(format_trace_summary(collection_agent))

        if target == "customer":
            return response

        if hop >= soft_cap:
            memory.set_state(agent_loop_blocked=True, agent_loop_count=hop)
            guard_state = collection_agent.run_turn("system loop guard", session_id=session_id)
            return str(guard_state.get("response", response))

        if target == "self":
            current_input = response
            continue

        if target == "discount_planning_agent":
            handoff_payload = (
                state.get("handoff_payload")
                if isinstance(state.get("handoff_payload"), dict)
                else {
                    "case_id": str(memory.state.get("active_case_id", "COLL-1001")),
                    "reason_for_handoff": "Need discount planning recommendation",
                    "current_plan": memory.state.get("current_plan"),
                    "hardship_reason": memory.state.get("hardship_reason"),
                }
            )
            discount_output = discount_agent.run(handoff_payload)
            memory.set_state(discount_recommendation=discount_output, agent_loop_count=hop)
            current_input = (
                f"collections emi restructuring recommendation ready for case "
                f"{handoff_payload.get('case_id', memory.state.get('active_case_id', 'COLL-1001'))}"
            )
            continue

        return response

    memory.set_state(agent_loop_blocked=True, agent_loop_count=hard_cap)
    guard_state = collection_agent.run_turn("system hard loop guard", session_id=session_id)
    return str(
        guard_state.get(
            "response",
            "I could not complete internal coordination in time. Please choose one next step: pay now, revise plan, or schedule follow-up.",
        )
    )


def interactive(
    agent: CollectionAgent,
    discount_agent: DiscountPlanningAgent,
    session_id: str,
    trace_readable: bool,
    soft_cap: int,
    hard_cap: int,
) -> None:
    print("Collection Agent demo interactive mode. Type 'exit' to stop.")
    while True:
        try:
            text = input("you> ").strip()
        except EOFError:
            print()
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break
        output = _route_internal_turn(
            collection_agent=agent,
            discount_agent=discount_agent,
            session_id=session_id,
            initial_input=text,
            soft_cap=soft_cap,
            hard_cap=hard_cap,
            trace_readable=trace_readable,
        )
        print(f"agent> {output}")


def main() -> None:
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    bootstrap_args, _ = bootstrap.parse_known_args()
    config_path = Path(bootstrap_args.config)
    config = load_collection_config(config_path)

    parser = build_parser({"config_path": str(config_path)})
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    llm = build_llm(config, cli_openai_api_key=args.openai_api_key, force_disable=args.disable_llm)
    trace_sink = build_trace_sink(args, base_dir, config)
    agent = CollectionAgent(
        repository=CollectionRepository(runtime_dir=base_dir / "runtime"),
        data_store=CollectionDataStore(base_dir=base_dir),
        llm=llm,
        trace_sink=trace_sink,
        trace_output_dir=base_dir / "runtime" / "traces",
    )
    discount_agent = DiscountPlanningAgent(llm=llm)

    if args.interactive:
        soft_cap = max(1, int(args.agent_hop_soft_cap))
        hard_cap = max(soft_cap, int(args.agent_hop_hard_cap))
        interactive(
            agent,
            discount_agent,
            args.session_id,
            args.trace_readable,
            soft_cap,
            hard_cap,
        )
        return
    if not args.message:
        raise SystemExit("message is required unless --interactive is used")

    print(agent.run(args.message, session_id=args.session_id))
    if args.trace_readable:
        print(format_trace_summary(agent))


if __name__ == "__main__":
    main()
