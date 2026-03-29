from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class AppSettings:
    db_path: Path
    log_path: Path
    policy_path: Path
    source_mode: str
    gmail_seed_path: Path
    classifier_mode: str
    llm_enabled: bool
    whatsapp_mode: str
    whatsapp_allowlist: tuple[str, ...]
    notification_destination: str
    viewer_host: str
    viewer_port: int
    poll_seconds: int

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            db_path=Path(os.getenv("MAILMIND_DB_PATH", "data/mailmind.db")),
            log_path=Path(os.getenv("MAILMIND_LOG_PATH", "data/logs/audit.jsonl")),
            policy_path=Path(os.getenv("MAILMIND_POLICY_PATH", "policies/default_policy.yaml")),
            source_mode=os.getenv("MAILMIND_SOURCE", "fake"),
            gmail_seed_path=Path(os.getenv("MAILMIND_GMAIL_SEED_PATH", "data/seed/demo_messages.json")),
            classifier_mode=os.getenv("MAILMIND_CLASSIFIER_MODE", "rules"),
            llm_enabled=_env_bool("MAILMIND_LLM_ENABLED", False),
            whatsapp_mode=os.getenv("MAILMIND_WHATSAPP_MODE", "fake"),
            whatsapp_allowlist=tuple(
                item.strip()
                for item in os.getenv("MAILMIND_WHATSAPP_ALLOWLIST", "").split(",")
                if item.strip()
            ),
            notification_destination=os.getenv("MAILMIND_NOTIFICATION_DESTINATION", ""),
            viewer_host=os.getenv("MAILMIND_VIEWER_HOST", "127.0.0.1"),
            viewer_port=int(os.getenv("MAILMIND_VIEWER_PORT", "8000")),
            poll_seconds=int(os.getenv("MAILMIND_POLL_SECONDS", "300")),
        )

