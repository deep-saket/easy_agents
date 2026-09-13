# Orchestrator Agent

Status: placeholder; not runnable.

This name reserves a future routing and orchestration agent that selects concrete agents. The current package contains only `agents/orchestrator/__init__.py`; it has no registry, router, graph, handoff protocol, CLI, or tests.

The repository does support in-process composition through `AgentNode`, and Collection Agent has an application-specific routing loop. Neither is the generic orchestrator planned for the platform. See [Create an Agent](../guides/create-an-agent.md) for current composition and the [Offline Agent Platform Roadmap](../plans/offline-agent-platform-roadmap.md) for the target design.
