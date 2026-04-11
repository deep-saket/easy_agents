"""Created: 2026-03-31

Purpose: Implements the config module for the shared utils platform layer.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_str(name: str) -> str | None:
    value = os.getenv(name)
    return value if value is not None else None


def _env_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value is not None else None


def _env_csv(name: str) -> tuple[str, ...] | None:
    value = os.getenv(name)
    if value is None:
        return None
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            nested = _compact_dict(value)
            if nested:
                compacted[key] = nested
            continue
        if value is not None:
            compacted[key] = value
    return compacted


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


class PathSettings(BaseModel):
    """Defines framework-level file paths."""

    db_path: Path = Path("data/easy_agent.duckdb")
    log_path: Path = Path("data/logs/audit.jsonl")
    policy_path: Path = Path("policies/default_policy.yaml")
    gmail_seed_path: Path = Path("data/seed/demo_messages.json")
    tool_catalog_path: Path = Path("data/tool_catalog.json")
    memory_cold_path: Path = Path("data/memory/cold_memories.jsonl")
    sleeping_tasks_path: Path = Path("data/memory/sleeping_tasks.jsonl")
    memory_tables_path: Path = Path("config/memory_tables.yaml")
    memory_policies_path: Path = Path("config/memory_policies.yaml")


class RuntimeSettings(BaseModel):
    """Defines general runtime settings."""

    source_mode: str = "fake"
    classifier_mode: str = "rules"
    llm_enabled: bool = False
    poll_seconds: int = 300


class NotificationSettings(BaseModel):
    """Defines outbound-notification settings."""

    whatsapp_mode: str = "fake"
    whatsapp_allowlist: tuple[str, ...] = Field(default_factory=tuple)
    notification_destination: str = ""


class ViewerSettings(BaseModel):
    """Defines local viewer settings."""

    host: str = "127.0.0.1"
    port: int = 8000


class LLMSettings(BaseModel):
    """Defines default LLM settings."""

    provider: str = "huggingface"
    model_name: str = "Qwen/Qwen3-1.7B"
    device_map: str = "auto"
    torch_dtype: str = "auto"
    max_new_tokens: int | None = None
    enable_thinking: bool = True


class PlannerSettings(BaseModel):
    """Defines planner-model settings."""

    enabled: bool = False
    provider: str = "function_gemma"
    model_name: str = "google/functiongemma-270m-it"
    device_map: str = "auto"
    torch_dtype: str = "auto"
    max_new_tokens: int | None = None


class MemorySettings(BaseModel):
    """Defines memory-system settings."""

    hot_cache_size: int = 256
    archive_after_days: int = 30
    escalation_step_count: int = 3
    confidence_threshold: float = 0.5
    similarity_enabled: bool = False
    similarity_backend: str = "none"
    embedding_provider: str = "sentence_transformer"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    hybrid_search_enabled: bool = False
    vector_top_k: int = 20


class IntegrationSettings(BaseModel):
    """Defines external integration settings."""

    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""


class AppSettings(BaseModel):
    """Defines the framework application settings."""

    config_path: Path = Path("config/easy_agent.yaml")
    paths: PathSettings = Field(default_factory=PathSettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    viewer: ViewerSettings = Field(default_factory=ViewerSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    planner: PlannerSettings = Field(default_factory=PlannerSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    integrations: IntegrationSettings = Field(default_factory=IntegrationSettings)

    @classmethod
    def from_env(cls) -> "AppSettings":
        """Builds settings from config file plus environment overrides."""

        _load_dotenv(Path(".env"))
        config_path = Path(os.getenv("EASY_AGENT_CONFIG_PATH", "config/easy_agent.yaml"))
        base_data = cls._load_config_file(config_path)
        merged = cls._merge_dicts(base_data, cls._env_overrides())
        merged["config_path"] = config_path
        return cls.model_validate(merged)

    @staticmethod
    def _load_config_file(config_path: Path) -> dict[str, Any]:
        if not config_path.exists():
            return {}
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"Config file {config_path} must contain a mapping at the top level.")
        return data

    @staticmethod
    def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            current = merged.get(key)
            if isinstance(current, dict) and isinstance(value, dict):
                merged[key] = AppSettings._merge_dicts(current, value)
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _env_overrides() -> dict[str, Any]:
        return _compact_dict(
            {
                "paths": {
                    "db_path": _env_str("EASY_AGENT_DB_PATH"),
                    "log_path": _env_str("EASY_AGENT_LOG_PATH"),
                    "policy_path": _env_str("EASY_AGENT_POLICY_PATH"),
                    "gmail_seed_path": _env_str("EASY_AGENT_GMAIL_SEED_PATH"),
                    "tool_catalog_path": _env_str("EASY_AGENT_TOOL_CATALOG_PATH"),
                    "memory_cold_path": _env_str("EASY_AGENT_MEMORY_COLD_PATH"),
                    "sleeping_tasks_path": _env_str("EASY_AGENT_SLEEPING_TASKS_PATH"),
                    "memory_tables_path": _env_str("EASY_AGENT_MEMORY_TABLES_PATH"),
                    "memory_policies_path": _env_str("EASY_AGENT_MEMORY_POLICIES_PATH"),
                },
                "runtime": {
                    "source_mode": _env_str("EASY_AGENT_SOURCE"),
                    "classifier_mode": _env_str("EASY_AGENT_CLASSIFIER_MODE"),
                    "llm_enabled": _env_bool("EASY_AGENT_LLM_ENABLED", False)
                    if os.getenv("EASY_AGENT_LLM_ENABLED") is not None
                    else None,
                    "poll_seconds": _env_int("EASY_AGENT_POLL_SECONDS"),
                },
                "notifications": {
                    "whatsapp_mode": _env_str("EASY_AGENT_WHATSAPP_MODE"),
                    "whatsapp_allowlist": _env_csv("EASY_AGENT_WHATSAPP_ALLOWLIST"),
                    "notification_destination": _env_str("EASY_AGENT_NOTIFICATION_DESTINATION"),
                },
                "viewer": {
                    "host": _env_str("EASY_AGENT_VIEWER_HOST"),
                    "port": _env_int("EASY_AGENT_VIEWER_PORT"),
                },
                "llm": {
                    "provider": _env_str("EASY_AGENT_LLM_PROVIDER"),
                    "model_name": _env_str("EASY_AGENT_LLM_MODEL_NAME"),
                    "device_map": _env_str("EASY_AGENT_LLM_DEVICE_MAP"),
                    "torch_dtype": _env_str("EASY_AGENT_LLM_TORCH_DTYPE"),
                    "max_new_tokens": _env_int("EASY_AGENT_LLM_MAX_NEW_TOKENS"),
                    "enable_thinking": _env_bool("EASY_AGENT_LLM_THINKING", False)
                    if os.getenv("EASY_AGENT_LLM_THINKING") is not None
                    else None,
                },
                "planner": {
                    "enabled": _env_bool("EASY_AGENT_PLANNER_ENABLED", False)
                    if os.getenv("EASY_AGENT_PLANNER_ENABLED") is not None
                    else None,
                    "provider": _env_str("EASY_AGENT_PLANNER_PROVIDER"),
                    "model_name": _env_str("EASY_AGENT_PLANNER_MODEL_NAME"),
                    "device_map": _env_str("EASY_AGENT_PLANNER_DEVICE_MAP"),
                    "torch_dtype": _env_str("EASY_AGENT_PLANNER_TORCH_DTYPE"),
                    "max_new_tokens": _env_int("EASY_AGENT_PLANNER_MAX_NEW_TOKENS"),
                },
                "memory": {
                    "hot_cache_size": _env_int("EASY_AGENT_MEMORY_HOT_CACHE_SIZE"),
                    "archive_after_days": _env_int("EASY_AGENT_MEMORY_ARCHIVE_AFTER_DAYS"),
                    "escalation_step_count": _env_int("EASY_AGENT_MEMORY_ESCALATION_STEP_COUNT"),
                    "confidence_threshold": float(os.getenv("EASY_AGENT_MEMORY_CONFIDENCE_THRESHOLD"))
                    if os.getenv("EASY_AGENT_MEMORY_CONFIDENCE_THRESHOLD") is not None
                    else None,
                    "similarity_enabled": _env_bool("EASY_AGENT_MEMORY_SIMILARITY_ENABLED", False)
                    if os.getenv("EASY_AGENT_MEMORY_SIMILARITY_ENABLED") is not None
                    else None,
                    "similarity_backend": _env_str("EASY_AGENT_MEMORY_SIMILARITY_BACKEND"),
                    "embedding_provider": _env_str("EASY_AGENT_MEMORY_EMBEDDING_PROVIDER"),
                    "embedding_model": _env_str("EASY_AGENT_MEMORY_EMBEDDING_MODEL"),
                    "hybrid_search_enabled": _env_bool("EASY_AGENT_MEMORY_HYBRID_SEARCH_ENABLED", False)
                    if os.getenv("EASY_AGENT_MEMORY_HYBRID_SEARCH_ENABLED") is not None
                    else None,
                    "vector_top_k": _env_int("EASY_AGENT_MEMORY_VECTOR_TOP_K"),
                },
                "integrations": {
                    "gmail_client_id": _env_str("EASY_AGENT_GMAIL_CLIENT_ID"),
                    "gmail_client_secret": _env_str("EASY_AGENT_GMAIL_CLIENT_SECRET"),
                    "twilio_account_sid": _env_str("TWILIO_ACCOUNT_SID"),
                    "twilio_auth_token": _env_str("TWILIO_AUTH_TOKEN"),
                    "twilio_whatsapp_from": _env_str("EASY_AGENT_TWILIO_WHATSAPP_FROM"),
                },
            }
        )

    @property
    def db_path(self) -> Path:
        return self.paths.db_path

    @property
    def log_path(self) -> Path:
        return self.paths.log_path

    @property
    def policy_path(self) -> Path:
        return self.paths.policy_path

    @property
    def gmail_seed_path(self) -> Path:
        return self.paths.gmail_seed_path

    @property
    def tool_catalog_path(self) -> Path:
        return self.paths.tool_catalog_path

    @property
    def memory_cold_path(self) -> Path:
        return self.paths.memory_cold_path

    @property
    def sleeping_tasks_path(self) -> Path:
        return self.paths.sleeping_tasks_path

    @property
    def memory_tables_path(self) -> Path:
        return self.paths.memory_tables_path

    @property
    def memory_policies_path(self) -> Path:
        return self.paths.memory_policies_path

    @property
    def source_mode(self) -> str:
        return self.runtime.source_mode

    @property
    def classifier_mode(self) -> str:
        return self.runtime.classifier_mode

    @property
    def llm_enabled(self) -> bool:
        return self.runtime.llm_enabled

    @property
    def poll_seconds(self) -> int:
        return self.runtime.poll_seconds

    @property
    def whatsapp_mode(self) -> str:
        return self.notifications.whatsapp_mode

    @property
    def whatsapp_allowlist(self) -> tuple[str, ...]:
        return self.notifications.whatsapp_allowlist

    @property
    def notification_destination(self) -> str:
        return self.notifications.notification_destination

    @property
    def viewer_host(self) -> str:
        return self.viewer.host

    @property
    def viewer_port(self) -> int:
        return self.viewer.port

__all__ = ["AppSettings"]
