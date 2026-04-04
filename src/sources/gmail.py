"""Created: 2026-04-04

Purpose: Implements a Gmail-backed email source.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import getaddresses, parsedate_to_datetime, parseaddr
from pathlib import Path
from typing import Any, Protocol

from src.schemas.domain import EmailMessage


class GmailMessagesGetRequest(Protocol):
    """Describes the Gmail message-get request surface used by the source."""

    def execute(self) -> dict[str, Any]:
        ...


class GmailMessagesListRequest(Protocol):
    """Describes the Gmail message-list request surface used by the source."""

    def execute(self) -> dict[str, Any]:
        ...


class GmailMessagesResource(Protocol):
    """Describes the Gmail messages resource surface used by the source."""

    def list(self, *, userId: str, q: str | None = None, labelIds: list[str] | None = None, maxResults: int = 50) -> GmailMessagesListRequest:
        ...

    def get(self, *, userId: str, id: str, format: str = "full") -> GmailMessagesGetRequest:
        ...


class GmailUsersResource(Protocol):
    """Describes the Gmail users resource surface used by the source."""

    def messages(self) -> GmailMessagesResource:
        ...


class GmailServiceProtocol(Protocol):
    """Describes the Gmail service surface used by the source."""

    def users(self) -> GmailUsersResource:
        ...


@dataclass(slots=True)
class GmailEmailSource:
    """Fetches email messages from Gmail using the Google API.

    The source is intentionally dependency-injected:

    - callers may pass a ready-made Gmail service object
    - otherwise the source can build one from explicit credential/token paths

    No framework-global config is read here.
    """

    service: GmailServiceProtocol | None = None
    credentials_path: Path | None = None
    token_path: Path | None = None
    client_id: str | None = None
    client_secret: str | None = None
    user_id: str = "me"
    query: str | None = None
    label_ids: list[str] = field(default_factory=list)
    max_results: int = 50

    def fetch_new_messages(self) -> list[EmailMessage]:
        """Fetches and normalizes Gmail messages into framework email models."""

        messages_api = self._get_service().users().messages()
        response = messages_api.list(
            userId=self.user_id,
            q=self.query,
            labelIds=self.label_ids or None,
            maxResults=self.max_results,
        ).execute()
        items = response.get("messages", [])
        emails: list[EmailMessage] = []
        for item in items:
            message_id = str(item.get("id", "")).strip()
            if not message_id:
                continue
            raw_message = messages_api.get(userId=self.user_id, id=message_id, format="full").execute()
            emails.append(self._normalize_message(raw_message))
        return emails

    def _get_service(self) -> GmailServiceProtocol:
        if self.service is not None:
            return self.service
        self.service = self._build_service()
        return self.service

    def _build_service(self) -> GmailServiceProtocol:
        if self.token_path is None:
            raise ValueError("GmailEmailSource requires `token_path` when building a Gmail service.")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Google Gmail client dependencies are not installed. Install with `pip install -e \".[gmail]\"`."
            ) from exc

        scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
        credentials = None
        if self.token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(self.token_path), scopes)
        if credentials is None or not credentials.valid:
            if credentials is not None and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                client_config = self._oauth_client_config()
                if self.credentials_path is not None:
                    flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), scopes)
                elif client_config is not None:
                    flow = InstalledAppFlow.from_client_config(client_config, scopes)
                else:
                    raise ValueError(
                        "GmailEmailSource requires either `credentials_path` or `client_id` + `client_secret`."
                    )
                credentials = flow.run_local_server(port=0, open_browser=False)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)

    def _oauth_client_config(self) -> dict[str, Any] | None:
        if not self.client_id or not self.client_secret:
            return None
        return {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

    def _normalize_message(self, payload: dict[str, Any]) -> EmailMessage:
        headers = self._header_map(payload.get("payload", {}))
        from_name, from_email = self._parse_from(headers.get("from"))
        recipients = self._parse_recipients(headers.get("to"))
        body_text = self._extract_body(payload.get("payload", {}), mime_type="text/plain") or payload.get("snippet", "")
        body_html = self._extract_body(payload.get("payload", {}), mime_type="text/html")
        received_at = self._parse_received_at(payload, headers.get("date"))
        return EmailMessage(
            source_id=str(payload.get("id", "")),
            thread_id=str(payload.get("threadId", "")) or None,
            from_name=from_name,
            from_email=from_email or "",
            to=recipients,
            subject=headers.get("subject", ""),
            body_text=body_text,
            body_html=body_html,
            received_at=received_at,
            labels=[str(label) for label in payload.get("labelIds", [])],
            raw=payload,
        )

    @staticmethod
    def _header_map(payload: dict[str, Any]) -> dict[str, str]:
        headers: dict[str, str] = {}
        for header in payload.get("headers", []):
            name = str(header.get("name", "")).strip().lower()
            if not name:
                continue
            headers[name] = str(header.get("value", ""))
        return headers

    @staticmethod
    def _parse_from(value: str | None) -> tuple[str | None, str | None]:
        if not value:
            return None, None
        name, email = parseaddr(value)
        return name or None, email or None

    @staticmethod
    def _parse_recipients(value: str | None) -> list[str]:
        if not value:
            return []
        return [address for _, address in getaddresses([value]) if address]

    def _extract_body(self, payload: dict[str, Any], *, mime_type: str) -> str | None:
        if payload.get("mimeType") == mime_type:
            data = self._body_data(payload.get("body", {}))
            if data:
                return data
        for part in payload.get("parts", []) or []:
            data = self._extract_body(part, mime_type=mime_type)
            if data:
                return data
        return None

    @staticmethod
    def _body_data(body: dict[str, Any]) -> str | None:
        data = body.get("data")
        if not data:
            return None
        padding = "=" * (-len(data) % 4)
        decoded = base64.urlsafe_b64decode((data + padding).encode("ascii"))
        return decoded.decode("utf-8", errors="replace")

    @staticmethod
    def _parse_received_at(payload: dict[str, Any], date_header: str | None) -> datetime:
        if date_header:
            try:
                parsed = parsedate_to_datetime(date_header)
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=UTC)
                return parsed.astimezone(UTC)
            except (TypeError, ValueError, IndexError):
                pass
        internal_date = payload.get("internalDate")
        if internal_date is not None:
            try:
                return datetime.fromtimestamp(int(internal_date) / 1000, tz=UTC)
            except (TypeError, ValueError):
                pass
        return datetime.now(UTC)


__all__ = ["GmailEmailSource"]
