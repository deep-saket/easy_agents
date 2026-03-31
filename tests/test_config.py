"""Created: 2026-03-30

Purpose: Tests the config behavior.
"""

from pathlib import Path

from mailmind.config import AppSettings


def test_app_settings_load_from_config_file(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "mailmind.yaml"
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
    monkeypatch.setenv("MAILMIND_CONFIG_PATH", str(config_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAILMIND_DB_PATH", raising=False)
    monkeypatch.delenv("MAILMIND_POLL_SECONDS", raising=False)
    monkeypatch.delenv("MAILMIND_NOTIFICATION_DESTINATION", raising=False)
    monkeypatch.delenv("MAILMIND_WHATSAPP_ALLOWLIST", raising=False)
    monkeypatch.delenv("MAILMIND_VIEWER_PORT", raising=False)
    monkeypatch.delenv("MAILMIND_TWILIO_WHATSAPP_FROM", raising=False)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MAILMIND_GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("MAILMIND_GMAIL_CLIENT_SECRET", raising=False)

    settings = AppSettings.from_env()

    assert settings.db_path == Path("data/custom.db")
    assert settings.poll_seconds == 42
    assert settings.notification_destination == "+910000000001"
    assert settings.whatsapp_allowlist == ("+910000000001",)
    assert settings.viewer_port == 9000


def test_env_overrides_config_file(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "mailmind.yaml"
    config_path.write_text(
        """
notifications:
  notification_destination: "+910000000001"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("MAILMIND_CONFIG_PATH", str(config_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAILMIND_NOTIFICATION_DESTINATION", "+919999999999")

    settings = AppSettings.from_env()

    assert settings.notification_destination == "+919999999999"
