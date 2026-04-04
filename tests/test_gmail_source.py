"""Created: 2026-04-04

Purpose: Tests the Gmail-backed email source adapter.
"""

from __future__ import annotations

import base64
from src.sources.gmail import GmailEmailSource


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


class _FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _FakeMessages:
    def __init__(self, listing, messages):
        self.listing = listing
        self.messages = messages

    def list(self, **kwargs):
        del kwargs
        return _FakeRequest(self.listing)

    def get(self, **kwargs):
        return _FakeRequest(self.messages[kwargs["id"]])


class _FakeUsers:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages


class _FakeService:
    def __init__(self, listing, messages):
        self._users = _FakeUsers(_FakeMessages(listing, messages))

    def users(self):
        return self._users

def test_gmail_source_normalizes_google_api_messages() -> None:
    listing = {"messages": [{"id": "gmail-1"}]}
    message_payload = {
        "id": "gmail-1",
        "threadId": "thread-1",
        "internalDate": "1712223000000",
        "snippet": "plain fallback",
        "labelIds": ["INBOX", "IMPORTANT"],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Recruiter <talent@deepmind.com>"},
                {"name": "To", "value": "user@example.com"},
                {"name": "Subject", "value": "Research role"},
                {"name": "Date", "value": "Thu, 04 Apr 2026 10:00:00 +0000"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": _b64("We are hiring.")}},
                {"mimeType": "text/html", "body": {"data": _b64("<p>We are hiring.</p>")}},
            ],
        },
    }
    source = GmailEmailSource(service=_FakeService(listing, {"gmail-1": message_payload}))

    messages = source.fetch_new_messages()

    assert len(messages) == 1
    message = messages[0]
    assert message.source_id == "gmail-1"
    assert message.thread_id == "thread-1"
    assert message.from_name == "Recruiter"
    assert message.from_email == "talent@deepmind.com"
    assert message.to == ["user@example.com"]
    assert message.subject == "Research role"
    assert message.body_text == "We are hiring."
    assert message.body_html == "<p>We are hiring.</p>"
    assert message.labels == ["INBOX", "IMPORTANT"]
