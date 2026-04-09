"""Created: 2026-03-30

Purpose: Tests the dotenv loading behavior.
"""

from pathlib import Path

from src.utils.config import AppSettings


def test_dotenv_file_is_loaded(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "easy_agent.yaml"
    config_path.write_text("{}", encoding="utf-8")
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                f"EASY_AGENT_CONFIG_PATH={config_path}",
                "EASY_AGENT_GMAIL_CLIENT_ID=test-gmail-client",
                "EASY_AGENT_TWILIO_ACCOUNT_SID=ACtest123",
                "EASY_AGENT_TWILIO_AUTH_TOKEN=test-token",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EASY_AGENT_GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("EASY_AGENT_TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("EASY_AGENT_TWILIO_AUTH_TOKEN", raising=False)

    settings = AppSettings.from_env()

    assert settings.integrations.gmail_client_id == "test-gmail-client"
    assert settings.integrations.twilio_account_sid == "ACtest123"
    assert settings.integrations.twilio_auth_token == "test-token"
