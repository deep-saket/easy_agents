"""Created: 2026-04-01

Purpose: Exposes the DuckDB-backed MailMind repository through shared storage.
"""

from __future__ import annotations

from src.mailmind.storage.repository import DuckDBMessageRepository as DuckDBStore

__all__ = ["DuckDBStore"]
