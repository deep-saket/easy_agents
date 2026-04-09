"""Created: 2026-04-09

Purpose: Implements a Gmail-backed email sender.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from email.message import EmailMessage as MimeEmailMessage
from pathlib import Path
from typing import Any, Protocol

from src.schemas.domain import EmailMessage, ReplyDraft, SentEmail


class GmailMessagesSendRequest(Protocol):
    """Describes the Gmail message-send request surface used by the sender."""

    def execute(self) -> dict[str, Any]:
        ...


class GmailMessagesSendResource(Protocol):
    """Describes the Gmail messages send surface used by the sender."""

    def send(self, *, userId: str, body: dict[str, Any]) -> GmailMessagesSendRequest:
        ...


class GmailUsersSendResource(Protocol):
    """Describes the Gmail users resource surface used by the sender."""

    def messages(self) -> GmailMessagesSendResource:
        ...


class GmailSendServiceProtocol(Protocol):
    """Describes the Gmail service surface used by the sender."""

    def users(self) -> GmailUsersSendResource:
        ...


@dataclass(slots=True)
class GmailEmailSender:
    """Sends outbound email replies via Gmail using the Google API."""

    service: GmailSendServiceProtocol | None = None
    credentials_path: Path | None = None
    token_path: Path | None = None
    client_id: str | None = None
    client_secret: str | None = None
    user_id: str = "me"

    def send(
        self,
        *,
        message: EmailMessage,
        draft: ReplyDraft,
        recipients: list[str] | None = None,
        subject: str | None = None,
        body_text: str | None = None,
    ) -> SentEmail:
        resolved_recipients = recipients or [message.from_email]
        if not resolved_recipients:
            raise ValueError("At least one recipient is required to send an email.")
        resolved_subject = subject or draft.subject
        resolved_body = body_text or draft.body_text
        mime = MimeEmailMessage()
        mime["To"] = ", ".join(resolved_recipients)
        mime["Subject"] = resolved_subject
        if message.thread_id:
            mime["Thread-Topic"] = resolved_subject
        mime.set_content(resolved_body)

        payload = {
            "raw": base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii"),
        }
        if message.thread_id:
            payload["threadId"] = message.thread_id

        response = self._get_service().users().messages().send(userId=self.user_id, body=payload).execute()
        return SentEmail(
            message_id=message.id,
            draft_id=draft.id,
            provider_message_id=str(response.get("id", "")) or None,
            thread_id=str(response.get("threadId", "")) or message.thread_id,
            recipients=resolved_recipients,
            subject=resolved_subject,
            status="sent",
        )

    def _get_service(self) -> GmailSendServiceProtocol:
        if self.service is not None:
            return self.service
        self.service = self._build_service()
        return self.service

    def _build_service(self) -> GmailSendServiceProtocol:
        if self.token_path is None:
            raise ValueError("GmailEmailSender requires `token_path` when building a Gmail service.")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError(
                "Google Gmail client dependencies are not installed. Install with `pip install -e \".[gmail]\"`."
            ) from exc

        scopes = ["https://www.googleapis.com/auth/gmail.send"]
        credentials = None
        if self.token_path.exists():
            credentials = Credentials.from_authorized_user_file(str(self.token_path), scopes)
        if credentials is None or not credentials.valid:
            if credentials is not None and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                if self.credentials_path is not None:
                    flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), scopes)
                elif self.client_id and self.client_secret:
                    flow = InstalledAppFlow.from_client_config(
                        {
                            "installed": {
                                "client_id": self.client_id,
                                "client_secret": self.client_secret,
                                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                                "token_uri": "https://oauth2.googleapis.com/token",
                                "redirect_uris": ["http://localhost"],
                            }
                        },
                        scopes,
                    )
                else:
                    raise ValueError(
                        "GmailEmailSender requires either `credentials_path` or `client_id` + `client_secret`."
                    )
                credentials = flow.run_local_server(port=0, open_browser=False)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        return build("gmail", "v1", credentials=credentials, cache_discovery=False)


__all__ = ["GmailEmailSender"]
