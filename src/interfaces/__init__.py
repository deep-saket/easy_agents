"""Created: 2026-03-31

Purpose: Shared external interfaces.
"""

from src.interfaces.email import (
    ApprovalQueue,
    AuditLogStore,
    DraftGenerator,
    EmailSource,
    MessageClassifier,
    MessageRepository,
    Notifier,
    PolicyProvider,
    SupportsReprocess,
)
from src.interfaces.pipecat_runner import (
    PipecatNotInstalledError,
    PipecatRunnerConfig,
    build_runner_bot,
    build_transport_params,
    ensure_pipecat_available,
    run_pipecat_main,
)

__all__ = [
    "ApprovalQueue",
    "AuditLogStore",
    "DraftGenerator",
    "EmailSource",
    "MessageClassifier",
    "MessageRepository",
    "Notifier",
    "PolicyProvider",
    "PipecatNotInstalledError",
    "PipecatRunnerConfig",
    "SupportsReprocess",
    "build_runner_bot",
    "build_transport_params",
    "ensure_pipecat_available",
    "run_pipecat_main",
]
