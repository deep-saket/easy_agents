# Simple Conversation Agent

Status: working example.

The simple conversation agent is the lightweight concrete agent in the repository. It is primarily intended for endpoint, notebook, and framework demonstrations rather than as a general personal assistant.

It demonstrates:

- graph-based turn execution
- deterministic pre-model planning rules
- working-memory updates
- mock or Twilio WhatsApp interface integration
- trace logging

## Graph

```mermaid
flowchart LR
    Start(["Start"]) --> Retrieve["Retrieve memory"]
    Retrieve --> Plan["Conversation plan"]
    Plan --> Respond["Build response"]
    Respond --> WhatsApp["Send through channel"]
    WhatsApp --> Memory["Apply memory updates"]
    Memory --> End(["End"])
```

## Offline Example

Run from the repository root after installing the core dependencies:

```bash
python - <<'PY'
from agents.simple_conversation.agent import SimpleConversationAgent
from src.interfaces.whatsapp import MockWhatsAppInterface
from src.memory import WorkingMemory

memory = WorkingMemory(session_id="conversation-demo")
agent = SimpleConversationAgent(
    llm=None,
    memory=memory,
    whatsapp=MockWhatsAppInterface(),
)

print(agent.run("My name is Ada", session_id="conversation-demo"))
print(agent.run("What is my name?", session_id="conversation-demo"))
PY
```

Expected output:

```text
I'll remember that.
Your name is Ada.
```

The name storage and lookup paths are deterministic, so this example does not need a model or API key. Other messages fall through to the configured LLM; with `llm=None`, that fallback is intentionally limited.

## Full Environment Construction

`SimpleConversationAgent.from_env()` constructs a Qwen local-model adapter, working memory, a JSONL trace sink, and the configured WhatsApp adapter. It requires the local-model optional dependencies and may download model weights if they are not already cached:

```bash
python -m pip install -e ".[local-llm]"
```

Use `EASY_AGENT_WHATSAPP_MODE=fake` while developing. Twilio mode sends through an external service and requires valid Twilio configuration.

## Limitations

- There is no dedicated CLI entrypoint for this agent.
- Working memory is supplied as one object at construction time; this class is best used for a single logical session in demos.
- The default local model is much heavier than the deterministic smoke-test path.
- It demonstrates memory updates and channel delivery, but not tool execution. The [agent-authoring guide](../guides/create-an-agent.md) adds a validated tool.
