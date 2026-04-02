"""Created: 2026-03-31

Purpose: Implements the base agent module for the shared agents platform layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.platform_logging.structured_logger import StructuredLogger


class BaseAgent(ABC):
    """Defines the shared dependency shape for all concrete agents.

    This class exists to make the platform composition model explicit. A
    concrete agent is not expected to implement all logic itself. Instead, it
    coordinates a set of collaborating subsystems:

    - `llm`: the language-model adapter used for reasoning or generation
    - `planner`: the component that decides what the agent should do next
    - `tool_registry`: the catalog of tools the agent is allowed to call
    - `memory`: session-scoped working memory for the current interaction
    - `storage`: the agent's durable operational store
    - `logger`: structured logging for observability and audit
    - `memory_store`: long-term layered memory writes
    - `memory_retriever`: long-term layered memory reads

    The goal of this base class is clarity of composition, not behavior. The
    actual control loop belongs in concrete runtimes such as `GraphAgent` or
    future agent-specific runners.

    One subtle but important point is that an agent does not require an LLM in
    order to function. The platform allows two broad planning styles:

    - LLM-backed planning, where the planner asks a model to reason about the
      next step
    - deterministic planning, where the planner is rule-based or otherwise
      procedural

    In other words, `llm` is an optional dependency of the agent runtime, not a
    mandatory requirement for every agent turn.
    """

    def __init__(self, llm, planner, tool_registry, memory, storage, logger, memory_store=None, memory_retriever=None) -> None:
        """Stores the shared runtime dependencies for an agent instance.

        Args:
            llm: The language-model adapter used by the agent. This may be a
                local or remote model and can be `None` for purely rule-based
                agents.
            planner: The decision-making component that interprets user input
                and decides whether to respond directly, call a tool, or route
                elsewhere.
            tool_registry: The registry containing all tools available to this
                agent. The planner typically reasons over this tool set.
            memory: Working memory for the active interaction or session. This
                is short-lived state such as conversation history.
            storage: Durable agent-specific storage, such as the MailMind
                repository for emails, drafts, and approvals.
            logger: Structured logging backend used for observability.
            memory_store: Optional long-term memory write path for semantic,
                episodic, reflection, error, and task memory.
            memory_retriever: Optional long-term memory read path used when the
                agent needs historical context beyond the current session.
        """
        self.llm = llm
        self.planner = planner
        self.tool_registry = tool_registry
        self.memory = memory
        self.storage = storage
        self.logger = logger or StructuredLogger(type(self).__name__)
        self.memory_store = memory_store
        self.memory_retriever = memory_retriever

    def log_info(self, message: str, **context: object) -> None:
        """Writes one info-level structured log line for the agent.

        Args:
            message: Human-readable summary of the runtime event.
            **context: Additional structured fields to append to the message.
        """
        self._log(self.logger.info, message, **context)

    def log_debug(self, message: str, **context: object) -> None:
        """Writes one debug-level structured log line for the agent.

        Args:
            message: Human-readable summary of the runtime event.
            **context: Additional structured fields to append to the message.
        """
        self._log(self.logger.debug, message, **context)

    def log_warning(self, message: str, **context: object) -> None:
        """Writes one warning-level structured log line for the agent.

        Args:
            message: Human-readable summary of the runtime event.
            **context: Additional structured fields to append to the message.
        """
        self._log(self.logger.warning, message, **context)

    def log_exception(self, message: str, **context: object) -> None:
        """Writes one exception log line for the agent.

        Args:
            message: Human-readable summary of the runtime event.
            **context: Additional structured fields to append to the message.
        """
        self._log(self.logger.exception, message, **context)

    @staticmethod
    def _log(log_method: callable, message: str, **context: object) -> None:
        """Formats structured key-value context for a logging call.

        Args:
            log_method: Bound logger method such as `logger.info`.
            message: Human-readable log message.
            **context: Additional fields to serialize inline.
        """
        if context:
            rendered_context = " ".join(f"{key}={value!r}" for key, value in context.items())
            log_method("%s %s", message, rendered_context)
            return
        log_method("%s", message)

    @abstractmethod
    def run(self, user_input: str, session_id: str | None = None):
        """Executes one user-facing agent turn.

        Args:
            user_input: The raw input text from the user or upstream channel.
            session_id: Optional conversation/session identifier used to load
                or update working memory for multi-turn interactions.

        Returns:
            The concrete agent decides the return type, but in practice this is
            usually a user-facing response string or a structured result.
        """
        raise NotImplementedError
