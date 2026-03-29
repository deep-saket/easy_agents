from __future__ import annotations

from pathlib import Path

import yaml

from mailmind.core.interfaces import PolicyProvider
from mailmind.core.models import PolicyConfig


class YAMLPolicyProvider(PolicyProvider):
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> PolicyConfig:
        data = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        return PolicyConfig.model_validate(data)

