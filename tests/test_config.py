"""Created: 2026-03-30

Purpose: Tests the config behavior.
"""

from pathlib import Path

from src.utils.config import AppSettings


def test_app_settings_load_from_config_file(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "easy_agent.yaml"
    config_path.write_text(
        """
paths:
  db_path: data/custom.db
runtime:
  poll_seconds: 42
notifications:
  notification_destination: "+910000000001"
  whatsapp_allowlist:
    - "+910000000001"
viewer:
  port: 9000
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("EASY_AGENT_CONFIG_PATH", str(config_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EASY_AGENT_DB_PATH", raising=False)
    monkeypatch.delenv("EASY_AGENT_POLL_SECONDS", raising=False)
    monkeypatch.delenv("EASY_AGENT_NOTIFICATION_DESTINATION", raising=False)
    monkeypatch.delenv("EASY_AGENT_WHATSAPP_ALLOWLIST", raising=False)
    monkeypatch.delenv("EASY_AGENT_VIEWER_PORT", raising=False)
    monkeypatch.delenv("EASY_AGENT_GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("EASY_AGENT_GMAIL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("EASY_AGENT_TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("EASY_AGENT_TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("EASY_AGENT_TWILIO_WHATSAPP_FROM", raising=False)

    settings = AppSettings.from_env()

    assert settings.paths.db_path == Path("data/custom.db")
    assert settings.runtime.poll_seconds == 42
    assert settings.notifications.notification_destination == "+910000000001"
    assert settings.notifications.whatsapp_allowlist == ("+910000000001",)
    assert settings.viewer.port == 9000


def test_env_overrides_config_file(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "easy_agent.yaml"
    config_path.write_text(
        """
notifications:
  notification_destination: "+910000000001"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("EASY_AGENT_CONFIG_PATH", str(config_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EASY_AGENT_NOTIFICATION_DESTINATION", "+919999999999")

    settings = AppSettings.from_env()

    assert settings.notifications.notification_destination == "+919999999999"


def test_memory_vector_settings_load_from_env(monkeypatch) -> None:
    monkeypatch.setenv("EASY_AGENT_MEMORY_SIMILARITY_ENABLED", "true")
    monkeypatch.setenv("EASY_AGENT_MEMORY_SIMILARITY_BACKEND", "faiss")
    monkeypatch.setenv("EASY_AGENT_MEMORY_EMBEDDING_PROVIDER", "sentence_transformer")
    monkeypatch.setenv("EASY_AGENT_MEMORY_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    monkeypatch.setenv("EASY_AGENT_MEMORY_HYBRID_SEARCH_ENABLED", "true")
    monkeypatch.setenv("EASY_AGENT_MEMORY_VECTOR_TOP_K", "12")

    settings = AppSettings.from_env()

    assert settings.memory.similarity_enabled is True
    assert settings.memory.similarity_backend == "faiss"
    assert settings.memory.embedding_provider == "sentence_transformer"
    assert settings.memory.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert settings.memory.hybrid_search_enabled is True
    assert settings.memory.vector_top_k == 12


def test_mac_gemma_settings_load_from_environment(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "easy_agent.yaml"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("EASY_AGENT_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("EASY_AGENT_LLM_PROVIDER", "mac_gemma")
    monkeypatch.setenv("EASY_AGENT_LLM_MODEL_NAME", "gemma-4-E4B")
    monkeypatch.setenv("EASY_AGENT_LLM_MAX_NEW_TOKENS", "96")
    monkeypatch.setenv("EASY_AGENT_LLM_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("EASY_AGENT_LLM_TEMPERATURE", "0.2")
    monkeypatch.setenv("EASY_AGENT_LLM_TOP_P", "0.9")
    monkeypatch.setenv("GEMMA_API_BASE", "http://127.0.0.1:8080")
    monkeypatch.chdir(tmp_path)

    settings = AppSettings.from_env()

    assert settings.llm.provider == "mac_gemma"
    assert settings.llm.model_name == "gemma-4-E4B"
    assert settings.llm.max_new_tokens == 96
    assert settings.llm.base_url == "http://127.0.0.1:8080"
    assert settings.llm.timeout_seconds == 180
    assert settings.llm.temperature == 0.2
    assert settings.llm.top_p == 0.9
