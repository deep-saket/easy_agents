"""File-backed storage for global and user key-event memories."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class CollectionMemoryRepository:
    collection_runtime_dir: Path
    memory_dir: Path = field(init=False)
    global_path: Path = field(init=False)
    user_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.memory_dir = self.collection_runtime_dir / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.global_path = self.memory_dir / "global_key_event_memory.json"
        self.user_path = self.memory_dir / "user_key_event_memory.json"
        if not self.global_path.exists():
            self._write_json(self.global_path, self._default_global_payload())
        if not self.user_path.exists():
            self._write_json(self.user_path, self._default_user_payload())
        self._migrate_if_needed()

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return default
        return json.loads(content)

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    @staticmethod
    def _default_global_payload() -> dict[str, Any]:
        return {
            "version": 2,
            "updated_at": _utc_now_iso(),
            "event_counters": {},
            "successful_cues": [
                {
                    "cue_id": "collect-payment-link-after-dues-clarity",
                    "cue": "When user asks to pay now, send payment link right after dues explanation.",
                    "count": 3,
                    "last_seen": _utc_now_iso(),
                    "sample_signals": ["payment_intent: customer asked for immediate payment link"],
                    "sample_user_ids": ["CUST-2001", "CUST-2005"],
                }
            ],
            "unsuccessful_cues": [
                {
                    "cue_id": "avoid-hard-push-before-hardship-ack",
                    "cue": "Hard push fails when hardship is not acknowledged before options are discussed.",
                    "count": 2,
                    "last_seen": _utc_now_iso(),
                    "sample_signals": ["hardship_signal: cannot pay this month due to job loss"],
                    "sample_user_ids": ["CUST-2002"],
                }
            ],
        }

    @staticmethod
    def _default_user_payload() -> dict[str, Any]:
        return {
            "version": 2,
            "updated_at": _utc_now_iso(),
            "users": {
                "CUST-2001": {
                    "user_id": "CUST-2001",
                    "profile": {
                        "case_ids": ["COLL-1001"],
                        "preferred_channel": "sms",
                        "risk_band": "medium",
                    },
                    "memory": {
                        "latest_conversation_summary": (
                            "User acknowledged dues, requested payment link, and asked for confirmation once paid."
                        ),
                        "procedural_key_points": [
                            "Start with identity verification before discussing account specifics.",
                            "After dues explanation, provide one-click payment option.",
                        ],
                        "follow_up_considerations": [
                            "Check payment status before next reminder.",
                        ],
                        "last_outcome": "successful",
                        "last_case_id": "COLL-1001",
                        "updated_at": _utc_now_iso(),
                    },
                    "history": [
                        {
                            "session_id": "seed-cust-2001",
                            "summary": "Customer requested payment link and confirmed intent to clear dues.",
                            "procedural_key_points": [
                                "Offer payment link immediately after dues summary.",
                            ],
                            "outcome": "successful",
                            "created_at": _utc_now_iso(),
                        }
                    ],
                },
                "CUST-2002": {
                    "user_id": "CUST-2002",
                    "profile": {
                        "case_ids": ["COLL-1002"],
                        "preferred_channel": "voice",
                        "risk_band": "high",
                    },
                    "memory": {
                        "latest_conversation_summary": (
                            "User cited temporary hardship and asked for lower EMI options before committing."
                        ),
                        "procedural_key_points": [
                            "Lead with hardship acknowledgement before proposing collections action.",
                            "Evaluate discount/restructure options before requesting immediate payment.",
                        ],
                        "follow_up_considerations": [
                            "Begin next call with revised EMI options and promise capture path.",
                        ],
                        "last_outcome": "unsuccessful",
                        "last_case_id": "COLL-1002",
                        "updated_at": _utc_now_iso(),
                    },
                    "history": [
                        {
                            "session_id": "seed-cust-2002",
                            "summary": "Customer could not pay immediately; requested hardship restructuring.",
                            "procedural_key_points": [
                                "Avoid immediate payment push without restructuring option.",
                            ],
                            "outcome": "unsuccessful",
                            "created_at": _utc_now_iso(),
                        }
                    ],
                },
            },
        }

    def _migrate_if_needed(self) -> None:
        global_payload = self._read_json(self.global_path, self._default_global_payload())
        if int(global_payload.get("version", 1)) < 2:
            self._write_json(self.global_path, self._migrate_global_payload(global_payload))
        user_payload = self._read_json(self.user_path, self._default_user_payload())
        if int(user_payload.get("version", 1)) < 2:
            self._write_json(self.user_path, self._migrate_user_payload(user_payload))

    def _migrate_global_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        migrated = self._default_global_payload()
        old_events = payload.get("events", []) if isinstance(payload.get("events"), list) else []
        counters: dict[str, int] = {}
        unsuccessful_cues = list(migrated["unsuccessful_cues"])
        for row in old_events:
            if not isinstance(row, dict):
                continue
            event_type = str(row.get("event_type", "event")).strip().lower() or "event"
            count = int(row.get("count", 1) or 1)
            counters[event_type] = counters.get(event_type, 0) + count
            unsuccessful_cues.append(
                {
                    "cue_id": f"migrated-{event_type}",
                    "cue": event_type.replace("_", " "),
                    "count": count,
                    "last_seen": str(row.get("last_seen") or _utc_now_iso()),
                    "sample_signals": list(row.get("sample_signals", []))[-5:],
                    "sample_user_ids": [],
                }
            )
        migrated["event_counters"] = counters
        migrated["unsuccessful_cues"] = unsuccessful_cues[-25:]
        migrated["updated_at"] = _utc_now_iso()
        return migrated

    def _migrate_user_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        migrated = self._default_user_payload()
        users = payload.get("users", {}) if isinstance(payload.get("users"), dict) else {}
        converted_users = dict(migrated["users"])
        for session_id, row in users.items():
            if not isinstance(row, dict):
                continue
            user_id = str(row.get("user_id") or row.get("customer_id") or f"SESSION::{session_id}")
            key_events = [str(item) for item in list(row.get("key_events", []))[:20]]
            summary = str(row.get("summary", ""))
            converted_users[user_id] = {
                "user_id": user_id,
                "profile": {
                    "case_ids": [str(row.get("case_id"))] if row.get("case_id") else [],
                    "preferred_channel": "sms",
                    "risk_band": "unknown",
                },
                "memory": {
                    "latest_conversation_summary": summary,
                    "procedural_key_points": key_events[-8:],
                    "follow_up_considerations": [str(item) for item in list(row.get("next_considerations", []))[:8]],
                    "last_outcome": "neutral",
                    "last_case_id": str(row.get("case_id", "")),
                    "updated_at": str(row.get("updated_at") or _utc_now_iso()),
                },
                "history": [
                    {
                        "session_id": str(session_id),
                        "summary": summary,
                        "procedural_key_points": key_events[-8:],
                        "outcome": "neutral",
                        "created_at": str(row.get("updated_at") or _utc_now_iso()),
                    }
                ],
            }
        migrated["users"] = converted_users
        migrated["updated_at"] = _utc_now_iso()
        return migrated

    def upsert_global_cue(self, *, outcome: str, cue: str, signal: str, user_id: str | None = None) -> None:
        payload = self._read_json(self.global_path, self._default_global_payload())
        collection_key = "successful_cues" if outcome == "successful" else "unsuccessful_cues"
        rows = list(payload.get(collection_key, []))
        cue_id = cue.strip().lower().replace(" ", "-").replace(":", "-")[:80] or "generic-cue"
        row = next((item for item in rows if isinstance(item, dict) and item.get("cue_id") == cue_id), None)
        if row is None:
            row = {
                "cue_id": cue_id,
                "cue": cue,
                "count": 0,
                "last_seen": _utc_now_iso(),
                "sample_signals": [],
                "sample_user_ids": [],
            }
            rows.append(row)
        row["count"] = int(row.get("count", 0)) + 1
        row["last_seen"] = _utc_now_iso()
        signals = list(row.get("sample_signals", []))
        if signal and signal not in signals:
            signals.append(signal)
        row["sample_signals"] = signals[-5:]
        user_ids = [str(item) for item in list(row.get("sample_user_ids", [])) if str(item).strip()]
        if user_id and user_id not in user_ids:
            user_ids.append(user_id)
        row["sample_user_ids"] = user_ids[-5:]
        payload[collection_key] = rows[-40:]
        counters = dict(payload.get("event_counters", {}))
        outcome_key = f"conversation_outcome::{outcome}"
        counters[outcome_key] = int(counters.get(outcome_key, 0)) + 1
        payload["event_counters"] = counters
        payload["updated_at"] = _utc_now_iso()
        self._write_json(self.global_path, payload)

    def upsert_user_memory(self, *, user_id: str, session_id: str, user_memory: dict[str, Any]) -> None:
        payload = self._read_json(self.user_path, self._default_user_payload())
        users = dict(payload.get("users", {}))
        existing = dict(users.get(user_id, {}))
        profile = dict(existing.get("profile", {}))
        existing_case_ids = [str(item) for item in list(profile.get("case_ids", [])) if str(item).strip()]
        new_case_id = str(user_memory.get("case_id", "")).strip()
        if new_case_id and new_case_id not in existing_case_ids:
            existing_case_ids.append(new_case_id)
        profile["case_ids"] = existing_case_ids[-20:]
        preferred_channel = str(user_memory.get("preferred_channel", profile.get("preferred_channel", "sms")))
        profile["preferred_channel"] = preferred_channel
        if user_memory.get("risk_band") is not None:
            profile["risk_band"] = str(user_memory.get("risk_band"))

        memory_block = dict(existing.get("memory", {}))
        previous_points = [str(item) for item in list(memory_block.get("procedural_key_points", [])) if str(item).strip()]
        latest_points = [str(item) for item in list(user_memory.get("procedural_key_points", [])) if str(item).strip()]
        merged_points: list[str] = []
        for item in previous_points + latest_points:
            if item not in merged_points:
                merged_points.append(item)

        memory_block.update(
            {
                "latest_conversation_summary": str(user_memory.get("summary", "")),
                "procedural_key_points": merged_points[-20:],
                "follow_up_considerations": [str(item) for item in list(user_memory.get("follow_up_considerations", []))[:12]],
                "last_outcome": str(user_memory.get("conversation_outcome", "neutral")),
                "last_case_id": new_case_id,
                "last_trigger": dict(user_memory.get("trigger", {})) if isinstance(user_memory.get("trigger"), dict) else {},
                "updated_at": _utc_now_iso(),
            }
        )

        history = list(existing.get("history", []))
        history.append(
            {
                "session_id": session_id,
                "summary": str(user_memory.get("summary", "")),
                "procedural_key_points": latest_points[-12:],
                "outcome": str(user_memory.get("conversation_outcome", "neutral")),
                "created_at": _utc_now_iso(),
            }
        )

        users[user_id] = {
            "user_id": user_id,
            "profile": profile,
            "memory": memory_block,
            "history": history[-30:],
        }
        payload["users"] = users
        payload["updated_at"] = _utc_now_iso()
        self._write_json(self.user_path, payload)

    def get_user_memory_context(self, user_id: str) -> dict[str, Any] | None:
        payload = self._read_json(self.user_path, self._default_user_payload())
        users = payload.get("users", {})
        if not isinstance(users, dict):
            return None
        row = users.get(user_id)
        if not isinstance(row, dict):
            return None
        memory_block = dict(row.get("memory", {}))
        return {
            "user_id": user_id,
            "profile": dict(row.get("profile", {})),
            "latest_summary": str(memory_block.get("latest_conversation_summary", "")),
            "procedural_key_points": [str(item) for item in list(memory_block.get("procedural_key_points", []))[:20]],
            "follow_up_considerations": [str(item) for item in list(memory_block.get("follow_up_considerations", []))[:12]],
            "last_outcome": str(memory_block.get("last_outcome", "neutral")),
            "last_case_id": str(memory_block.get("last_case_id", "")),
        }

    def get_global_memory_context(self, *, limit: int = 5) -> dict[str, Any]:
        payload = self._read_json(self.global_path, self._default_global_payload())
        successful = sorted(
            [row for row in list(payload.get("successful_cues", [])) if isinstance(row, dict)],
            key=lambda row: int(row.get("count", 0)),
            reverse=True,
        )[:limit]
        unsuccessful = sorted(
            [row for row in list(payload.get("unsuccessful_cues", [])) if isinstance(row, dict)],
            key=lambda row: int(row.get("count", 0)),
            reverse=True,
        )[:limit]
        return {
            "updated_at": str(payload.get("updated_at", "")),
            "event_counters": dict(payload.get("event_counters", {})),
            "successful_cues": successful,
            "unsuccessful_cues": unsuccessful,
        }
