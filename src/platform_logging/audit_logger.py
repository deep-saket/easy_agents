"""Created: 2026-03-31

Purpose: Implements the audit logger module for the shared platform logging platform layer.
"""

from __future__ import annotations

from src.storage.json_store import JSONLAuditLogStore as AuditLogger

__all__ = ["AuditLogger"]
