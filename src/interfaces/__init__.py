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

__all__ = [
    "ApprovalQueue",
    "AuditLogStore",
    "DraftGenerator",
    "EmailSource",
    "MessageClassifier",
    "MessageRepository",
    "Notifier",
    "PolicyProvider",
    "SupportsReprocess",
]
