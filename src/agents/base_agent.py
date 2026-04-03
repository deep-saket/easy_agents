"""Created: 2026-03-31

Purpose: Implements the base agent module for the shared agents platform layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.platform_logging.structured_logger import StructuredLogger
from src.platform_logging.tracing import TraceSink


class BaseAgent(ABC):
    """Defines only the concerns shared by all agent runtimes.

    `BaseAgent` should stay small. It exists for the pieces that are truly
    runtime-agnostic across different agent implementations:

    - optional LLM access
    - stable agent identity
    - structured logging helpers
    - real-time trace sink integration

    It should not own graph wiring, planner contracts, tool registries, or
    storage topology. Those belong to the concrete runtime such as
    `GraphAgent`.
    """

    def __init__(
        self,
        *,
        llm=None,
        agent_name: str | None = None,
        logger=None,
        trace_sink: TraceSink | None = None,
    ) -> None:
        """Stores the minimal shared runtime dependencies for an agent.

        Args:
            llm: Optional language-model adapter for the runtime.
            agent_name: Stable runtime name used in logs and traces.
            logger: Structured logging backend used for observability.
            trace_sink: Optional real-time structured trace sink that receives
                one JSON event at a time during the forward pass.
        """
        self.llm = llm
        self.agent_name = agent_name or type(self).__name__.lower()
        self.logger = logger or StructuredLogger(type(self).__name__)
        self.trace_sink = trace_sink

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
