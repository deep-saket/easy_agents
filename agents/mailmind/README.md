# MailMind Agent

`MailMind` is the first concrete agent on top of the shared multi-agent platform.

MailMind-specific responsibilities:

- email ingestion
- email classification
- email search and summarization
- reply draft generation
- WhatsApp notification workflows

Shared abstractions such as LLMs, tools, planners, memory, storage, logging, and interfaces belong under `src/`.

Examples:

- Shared global LLM usage: `from llm.factory import LLMFactory`
- MailMind-specific override: `MailMindAgentApp.default_llm_example()`
- MailMind tools inherit the shared base: `from tools.base import BaseTool`

