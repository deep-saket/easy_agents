# Create an Agent

This guide shows the current code-first way to add an agent. It builds a completely offline calculator agent from the framework's real contracts: `BaseAgent`, `AgentState`, `BaseTool`, `ToolRegistry`, `ToolExecutor`, `ToolExecutionNode`, and LangGraph.

There is no working `agent.yaml` loader or `easy-agents create` command yet. Those are roadmap features. Today, an agent is a Python runtime that implements `run()` and explicitly wires its dependencies and graph.

## 1. Create the Package

From the repository root:

```bash
mkdir -p agents/calculator_agent
touch agents/calculator_agent/__init__.py
```

Add `agents/calculator_agent/agent.py` with the implementation below.

## 2. Implement a Tool-Using Graph

```python
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.agents.base_agent import BaseAgent
from src.memory import WorkingMemory
from src.nodes import AgentState, ToolExecutionNode
from src.schemas.tool_io import PlannerDecision, ToolCall
from src.tools import ToolExecutor, ToolRegistry
from src.tools.math import CalculateTool


class CalculatorAgent(BaseAgent):
    """Runs safe arithmetic through one deterministic graph."""

    def __init__(self) -> None:
        super().__init__(agent_name="calculator", llm=None)

        registry = ToolRegistry()
        registry.register(CalculateTool())
        self.tool_node = ToolExecutionNode(
            executor=ToolExecutor(registry=registry)
        )
        self.sessions: dict[str, WorkingMemory] = {}

        graph = StateGraph(AgentState)
        graph.add_node("plan", self._plan)
        graph.add_node("act", self.tool_node.execute)
        graph.add_node("respond", self._respond)
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "act")
        graph.add_edge("act", "respond")
        graph.add_edge("respond", END)
        self.graph = graph.compile()

    @staticmethod
    def _plan(state: AgentState) -> dict:
        return {
            "decision": PlannerDecision(
                thought="Use the safe arithmetic tool.",
                tool_call=ToolCall(
                    tool_name="calculate",
                    arguments={"expression": state["user_input"]},
                ),
            )
        }

    @staticmethod
    def _respond(state: AgentState) -> dict:
        result = state["observation"]["output"]["result"]
        return {"response": f"Result: {result}"}

    def run(self, user_input: str, session_id: str | None = None) -> str:
        session_key = session_id or "default"
        memory = self.sessions.setdefault(
            session_key,
            WorkingMemory(session_id=session_key),
        )
        memory.add_user_message(user_input)

        state = self.graph.invoke(
            {
                "session_id": session_key,
                "user_input": user_input,
                "memory": memory,
                "observations": [],
                "steps": 0,
            }
        )

        response = state["response"]
        memory.add_agent_message(response)
        return response
```

The graph has three responsibilities:

1. `plan` creates a typed request for the `calculate` tool.
2. `act` delegates validation, execution, and logging to the shared `ToolExecutionNode` and `ToolExecutor`.
3. `respond` converts the normalized observation into user-facing text.

The example deliberately uses a deterministic planner. It works without a model, provider key, or network connection.

## 3. Run It

```bash
python - <<'PY'
from agents.calculator_agent.agent import CalculatorAgent

agent = CalculatorAgent()
print(agent.run("12 * (3 + 4)", session_id="calculator-demo"))
PY
```

Expected output:

```text
Result: 84
```

`CalculateTool` parses a restricted arithmetic syntax tree; it does not call Python `eval()` and rejects arbitrary code.

## 4. Add a Test

Create `tests/test_calculator_agent.py`:

```python
from agents.calculator_agent.agent import CalculatorAgent


def test_calculator_agent_runs_a_tool() -> None:
    agent = CalculatorAgent()

    response = agent.run("12 * (3 + 4)", session_id="test-session")

    assert response == "Result: 84"
```

Run it from the repository root:

```bash
python -m pytest -q tests/test_calculator_agent.py
```

## 5. Create a New Tool

When the built-in tools do not cover the capability, define strict Pydantic schemas and subclass `BaseTool`:

```python
from pydantic import BaseModel, Field

from src.tools import BaseTool


class GreetingInput(BaseModel):
    name: str = Field(min_length=1)


class GreetingOutput(BaseModel):
    message: str


class GreetingTool(BaseTool[GreetingInput, GreetingOutput]):
    name = "greet"
    description = "Create a short greeting for a person."
    input_schema = GreetingInput
    output_schema = GreetingOutput

    def execute(self, input: GreetingInput) -> GreetingOutput:
        return GreetingOutput(message=f"Hello, {input.name}!")
```

Register it with the agent's `ToolRegistry`. Never put secrets in a tool description, graph state, log message, or model prompt. For a side-effecting tool—sending mail, changing a record, running a command—add an approval step and test both approval and denial paths.

## 6. Add Planning or an LLM

There are three current planning patterns:

- Deterministic node: choose a route or tool with Python rules, as in the calculator example.
- `ReactNode`: ask an object with `generate(system_prompt, user_prompt)` to return a direct response or structured tool choice.
- Specialized node: subclass or compose a node to add domain rules before and after model planning, as `ConversationNode` and several Collection Agent nodes do.

Use deterministic control for permissions, validation, limits, approvals, and irreversible actions. A model may recommend an action, but it should not be the only enforcement layer.

Local model adapters are available under `src.llm` after installing the `local-llm` extra. Local inference may be slow and model weights must already be downloaded for a truly offline run. Hosted adapters require their provider's key and network access.

## 7. Choose Memory Deliberately

For a small agent, `WorkingMemory` is enough. It holds recent messages and a session-scoped state dictionary in memory.

For persistent agents, decide separately:

- what belongs in working memory for the current conversation
- which events become typed long-term memory
- whether the hot cache, DuckDB warm layer, or JSONL cold layer is required
- how retrieval is filtered by agent, user, source, time, and tags
- what sensitive data must never be stored

Do not write every prompt and response into long-term memory by default. Use a `MemoryPolicy` and explicit retention rules. See [Memory Architecture](../architecture/memory-architecture.md).

## 8. Compose Agents

An existing agent can become a node in a parent graph:

```python
from src.nodes import AgentNode

calculator_node = AgentNode(
    agent=CalculatorAgent(),
    include_as_observation=True,
    include_as_response=False,
)
```

`AgentNode` calls the nested agent's `run()` method and derives a child session ID in the form `<parent-session>::delegate::<agent-name>`. This is useful for in-process composition, but it does not yet provide a registry, permissions, time budgets, durable handoff state, or process isolation.

## Agent Definition Checklist

Before calling a new agent complete, document and test:

- Purpose: one clear job and explicit non-goals
- Inputs and outputs: the `run()` contract and any structured state
- Graph: nodes, edges, routing conditions, loop and step limits
- Tools: schemas, errors, side effects, timeouts, idempotency, and approval needs
- Models: local or hosted provider, prompt contract, and deterministic fallback behavior
- Memory: session identity, stored types, retrieval filters, retention, and redaction
- Channels: CLI, API, WhatsApp, voice, or another adapter
- Observability: agent name, traces, tool logs, and failure context
- Tests: happy path, invalid input, tool failure, routing, memory isolation, and denied approval
- Usage docs: setup, configuration, one runnable command, expected output, and limitations

## Recommended Agent Directory

The repository does not enforce this structure yet, but it matches the more complete agents and scales beyond a single file:

```text
agents/<agent_name>/
  __init__.py
  agent.py
  main.py
  config.yml
  nodes/
  tools/
  prompts/
  tests/ or repository-level tests
  README.md
```

Start with only the files the agent needs. Keep reusable, domain-neutral contracts in `src/`; keep business rules and application-specific state under the concrete agent package.
