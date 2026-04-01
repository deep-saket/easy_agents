"""Created: 2026-03-30

Purpose: Tests the dotenv loading behavior.
"""

from pathlib import Path

from src.mailmind.config import AppSettings


def test_dotenv_file_is_loaded(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "mailmind.yaml"
    config_path.write_text("{}", encoding="utf-8")
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "\n".join(
            [
                f"MAILMIND_CONFIG_PATH={config_path}",
                "MAILMIND_GMAIL_CLIENT_ID=test-gmail-client",
                "TWILIO_ACCOUNT_SID=ACtest123",
                "TWILIO_AUTH_TOKEN=test-token",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAILMIND_GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)

    settings = AppSettings.from_env()

    assert settings.integrations.gmail_client_id == "test-gmail-client"
    assert settings.integrations.twilio_account_sid == "ACtest123"
    assert settings.integrations.twilio_auth_token == "test-token"
