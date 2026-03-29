from __future__ import annotations

import json
from pathlib import Path

from mailmind.core.models import EmailMessage


class FakeGmailEmailSource:
    def __init__(self, seed_path: Path) -> None:
        self._seed_path = seed_path

    def fetch_new_messages(self) -> list[EmailMessage]:
        records = json.loads(self._seed_path.read_text(encoding="utf-8"))
        return [EmailMessage.model_validate(record) for record in records]


class GmailEmailSource:
    def fetch_new_messages(self) -> list[EmailMessage]:
        # TODO: Implement Gmail OAuth, token caching, incremental sync, and MIME parsing.
        raise NotImplementedError("Real Gmail integration is not configured in v0.1.")

