"""Durable outbound callback queue with automatic dispatch and retries."""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone as fixed_timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DispatchFunction = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(slots=True)
class OutboundCallbackQueue:
    runtime_dir: Path
    dispatch: DispatchFunction | None = None
    poll_interval_seconds: float = 5.0
    expiry_grace_minutes: int = 30
    queue_path: Path = field(init=False)
    attempts_path: Path = field(init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _stop_event: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _worker: threading.Thread | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.queue_path = self.runtime_dir / "outbound_callback_jobs.json"
        self.attempts_path = self.runtime_dir / "outbound_call_attempts.json"
        self._ensure_file(self.queue_path)
        self._ensure_file(self.attempts_path)
        if self.dispatch is None:
            self.dispatch = self._dispatch_to_provider

    def schedule(
        self,
        *,
        case_id: str,
        customer_id: str,
        session_id: str,
        callback_time: str,
        timezone_name: str,
        phone: str,
        max_retries: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        scheduled_for = resolve_callback_datetime(
            callback_time,
            timezone_name=timezone_name,
            now=now,
        )
        now_utc = _as_utc(now or datetime.now(UTC))
        status = "scheduled" if scheduled_for > now_utc else "expired"
        with self._lock:
            jobs = self._read_rows(self.queue_path)
            for job in jobs:
                if (
                    job.get("case_id") == case_id
                    and job.get("scheduled_for") == scheduled_for.isoformat()
                    and job.get("status") in {"scheduled", "retrying", "dispatching"}
                ):
                    duplicate = dict(job)
                    duplicate["status"] = "duplicate"
                    return duplicate

            job = {
                "job_id": f"CALL-{uuid4().hex[:12].upper()}",
                "case_id": case_id,
                "customer_id": customer_id,
                "session_id": session_id,
                "phone": phone,
                "callback_time_text": callback_time,
                "scheduled_for": scheduled_for.isoformat(),
                "timezone": timezone_name,
                "status": status,
                "retry_count": 0,
                "max_retries": int(max_retries),
                "next_attempt_at": scheduled_for.isoformat(),
                "created_at": now_utc.isoformat(),
                "updated_at": now_utc.isoformat(),
                "provider_reference": None,
                "last_error": None,
                "cancel_reason": None,
            }
            jobs.append(job)
            self._write_rows(self.queue_path, jobs)
            return dict(job)

    def cancel(
        self,
        *,
        job_id: str | None = None,
        case_id: str | None = None,
        reason: str,
        now: datetime | None = None,
    ) -> list[str]:
        now_utc = _as_utc(now or datetime.now(UTC))
        cancelled: list[str] = []
        with self._lock:
            jobs = self._read_rows(self.queue_path)
            for job in jobs:
                matches = bool(job_id and job.get("job_id") == job_id) or bool(
                    case_id and job.get("case_id") == case_id
                )
                if not matches or job.get("status") not in {"scheduled", "retrying", "dispatching"}:
                    continue
                job["status"] = "cancelled"
                job["cancel_reason"] = reason
                job["updated_at"] = now_utc.isoformat()
                cancelled.append(str(job.get("job_id", "")))
            self._write_rows(self.queue_path, jobs)
        return cancelled

    def process_due(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        now_utc = _as_utc(now or datetime.now(UTC))
        processed: list[dict[str, Any]] = []
        with self._lock:
            jobs = self._read_rows(self.queue_path)
            for job in jobs:
                if job.get("status") not in {"scheduled", "retrying"}:
                    continue
                scheduled_for = datetime.fromisoformat(str(job["scheduled_for"]))
                next_attempt_at = datetime.fromisoformat(str(job.get("next_attempt_at") or job["scheduled_for"]))
                if now_utc > scheduled_for + timedelta(minutes=self.expiry_grace_minutes):
                    job["status"] = "expired"
                    job["updated_at"] = now_utc.isoformat()
                    processed.append(dict(job))
                    continue
                if next_attempt_at > now_utc:
                    continue

                job["status"] = "dispatching"
                job["updated_at"] = now_utc.isoformat()
                try:
                    result = (self.dispatch or self._dispatch_to_provider)(dict(job))
                    job["status"] = "dispatched"
                    job["provider_reference"] = str(result.get("provider_reference", "")).strip() or None
                    job["last_error"] = None
                    self._append_attempt(job=job, status="completed", result=result, now=now_utc)
                except Exception as exc:
                    job["retry_count"] = int(job.get("retry_count", 0)) + 1
                    job["last_error"] = str(exc)
                    if job["retry_count"] > int(job.get("max_retries", 3)):
                        job["status"] = "failed"
                    else:
                        job["status"] = "retrying"
                        delay_minutes = min(15, 2 ** (job["retry_count"] - 1))
                        job["next_attempt_at"] = (now_utc + timedelta(minutes=delay_minutes)).isoformat()
                    self._append_attempt(job=job, status="failed", result={"error": str(exc)}, now=now_utc)
                job["updated_at"] = now_utc.isoformat()
                processed.append(dict(job))
            self._write_rows(self.queue_path, jobs)
        return processed

    def start(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run,
            name="collection-outbound-callback-scheduler",
            daemon=True,
        )
        self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=max(1.0, self.poll_interval_seconds + 0.5))

    def _run(self) -> None:
        while not self._stop_event.wait(self.poll_interval_seconds):
            try:
                self.process_due()
            except Exception:
                continue

    def _dispatch_to_provider(self, job: dict[str, Any]) -> dict[str, Any]:
        webhook = os.getenv("COLLECTION_OUTBOUND_CALL_WEBHOOK", "").strip()
        if webhook:
            body = json.dumps(job, ensure_ascii=True).encode("utf-8")
            request = Request(
                webhook,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=15) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                return {
                    "provider": "webhook",
                    "provider_reference": response.headers.get("X-Request-Id", ""),
                    "status_code": int(response.status),
                    "response": response_body[:500],
                }

        account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        voice_from = os.getenv("EASY_AGENT_TWILIO_VOICE_FROM", "").strip()
        voice_url = os.getenv("EASY_AGENT_TWILIO_VOICE_URL", "").strip()
        if account_sid and auth_token and voice_from and voice_url:
            from twilio.rest import Client  # type: ignore[import-not-found]

            call = Client(account_sid, auth_token).calls.create(
                to=str(job["phone"]),
                from_=voice_from,
                url=voice_url,
            )
            return {
                "provider": "twilio",
                "provider_reference": str(call.sid),
                "status": str(getattr(call, "status", "queued")),
            }

        raise RuntimeError(
            "Outbound call provider is not configured. Set COLLECTION_OUTBOUND_CALL_WEBHOOK "
            "or TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, EASY_AGENT_TWILIO_VOICE_FROM, "
            "and EASY_AGENT_TWILIO_VOICE_URL."
        )

    def _append_attempt(
        self,
        *,
        job: dict[str, Any],
        status: str,
        result: dict[str, Any],
        now: datetime,
    ) -> None:
        rows = self._read_rows(self.attempts_path)
        rows.append(
            {
                "attempt_id": f"ATT-{uuid4().hex[:12].upper()}",
                "job_id": job.get("job_id"),
                "case_id": job.get("case_id"),
                "customer_id": job.get("customer_id"),
                "phone": job.get("phone"),
                "retry_count": job.get("retry_count", 0),
                "status": status,
                "result": result,
                "created_at": now.isoformat(),
            }
        )
        self._write_rows(self.attempts_path, rows)

    @staticmethod
    def _ensure_file(path: Path) -> None:
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")

    @staticmethod
    def _read_rows(path: Path) -> list[dict[str, Any]]:
        content = path.read_text(encoding="utf-8").strip()
        payload = json.loads(content) if content else []
        return [dict(row) for row in payload if isinstance(row, dict)]

    @staticmethod
    def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(rows, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        temporary.replace(path)


def resolve_callback_datetime(
    callback_time: str,
    *,
    timezone_name: str,
    now: datetime | None = None,
) -> datetime:
    timezone = _load_timezone(timezone_name)
    current = now or datetime.now(timezone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone)
    else:
        current = current.astimezone(timezone)

    text = re.sub(r"\s+", " ", callback_time.strip().lower())
    day_offset = 1 if "tomorrow" in text else 0
    weekday_names = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    target_date = (current + timedelta(days=day_offset)).date()
    for name, weekday in weekday_names.items():
        if name not in text:
            continue
        days_ahead = (weekday - current.weekday()) % 7
        if "next " in text or days_ahead == 0:
            days_ahead = days_ahead or 7
        target_date = (current + timedelta(days=days_ahead)).date()
        break

    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        if not 1 <= hour <= 12 or not 0 <= minute <= 59:
            raise ValueError(f"Invalid callback time: {callback_time}")
        if match.group(3) == "pm" and hour != 12:
            hour += 12
        elif match.group(3) == "am" and hour == 12:
            hour = 0
    elif "morning" in text:
        hour, minute = 9, 0
    elif "afternoon" in text:
        hour, minute = 14, 0
    elif "evening" in text:
        hour, minute = 18, 0
    elif "night" in text:
        hour, minute = 20, 0
    else:
        raise ValueError(f"Callback time is not specific enough to schedule: {callback_time}")

    local_value = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=timezone,
    )
    return local_value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _load_timezone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        fixed_offsets = {
            "Asia/Kolkata": fixed_timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata"),
            "UTC": UTC,
        }
        if timezone_name in fixed_offsets:
            return fixed_offsets[timezone_name]
        raise ValueError(
            f"Timezone data is unavailable for {timezone_name}. Install the tzdata package "
            "or use a supported configured timezone."
        )


__all__ = ["OutboundCallbackQueue", "resolve_callback_datetime"]
