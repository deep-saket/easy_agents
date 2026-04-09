# MailMind Agent

`MailMind` currently exposes classifier-specific helpers on top of the shared multi-agent platform.

Concrete package entrypoints:

- `from agents.mailmind import MailMindEmailClassifier`
- `from agents.mailmind import MailMindEmailClassificationPayload`

MailMind-specific responsibilities:

- email classification
- category prompt definitions
- classifier payload schemas

Shared abstractions such as LLMs, tools, planners, memory, storage, logging, and interfaces belong under `src/`.
