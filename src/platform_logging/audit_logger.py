"""Created: 2026-03-31

Purpose: Implements the audit logger module for the shared platform logging platform layer.
"""

from __future__ import annotations

from mailmind.logs.jsonl import JSONLAuditLogStore as AuditLogger

__all__ = ["AuditLogger"]
