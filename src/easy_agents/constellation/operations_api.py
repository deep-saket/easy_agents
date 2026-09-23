"""Read-only operations, history, replay, metrics, and SSE endpoints."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from easy_agents.observability import EventFilter, ObservabilityPipeline, Severity, TraceEvent


def create_operations_router(pipeline: ObservabilityPipeline) -> APIRouter:
    """Builds API routes backed by one shared observability pipeline."""

    router = APIRouter()

    @router.get("/api/operations/snapshot")
    def operations_snapshot() -> dict[str, Any]:
        return pipeline.snapshot()

    @router.get("/api/events")
    def events(
        after_sequence: int = Query(default=0, ge=0),
        before_sequence: int | None = Query(default=None, ge=1),
        limit: int = Query(default=200, ge=1, le=2_000),
        mission_id: str | None = None,
        run_id: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
        severity: Severity | None = None,
        entity_kind: str | None = None,
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        page = pipeline.events(
            EventFilter(
                after_sequence=after_sequence,
                before_sequence=before_sequence,
                limit=limit,
                mission_id=mission_id,
                run_id=run_id,
                event_type=event_type,
                status=status,
                severity=severity,
                entity_kind=entity_kind,
                entity_id=entity_id,
            )
        )
        next_cursor = page[-1].sequence if page else after_sequence
        return {
            "events": [item.model_dump(mode="json") for item in page],
            "next_cursor": next_cursor,
            "latest_sequence": pipeline.store.latest_sequence(),
        }

    @router.get("/api/events/stream")
    async def event_stream(
        request: Request,
        after_sequence: int | None = Query(default=None, ge=0),
        limit: int | None = Query(default=None, ge=1, le=2_000),
        mission_id: str | None = None,
        run_id: str | None = None,
        severity: Severity | None = None,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        cursor = after_sequence or 0
        if last_event_id:
            try:
                cursor = max(cursor, int(last_event_id))
            except ValueError:
                pass
        subscription = pipeline.hub.subscribe()
        generator = _stream_events(
            request=request,
            pipeline=pipeline,
            subscription=subscription,
            cursor=cursor,
            limit=limit,
            mission_id=mission_id,
            run_id=run_id,
            severity=severity,
        )
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/api/missions")
    def missions(limit: int = Query(default=50, ge=1, le=100)) -> dict[str, Any]:
        snapshot = pipeline.projector.snapshot()
        return {
            "missions": snapshot["missions"][:limit],
            "latest_sequence": snapshot["last_sequence"],
        }

    @router.get("/api/missions/{mission_id}")
    def mission(mission_id: str) -> dict[str, Any]:
        payload = pipeline.projector.mission(mission_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="Mission was not found.")
        return payload

    @router.get("/api/missions/{mission_id}/timeline")
    def mission_timeline(
        mission_id: str,
        after_sequence: int = Query(default=0, ge=0),
        limit: int = Query(default=1_000, ge=1, le=2_000),
    ) -> dict[str, Any]:
        if pipeline.projector.mission(mission_id) is None:
            raise HTTPException(status_code=404, detail="Mission was not found.")
        page = pipeline.events(
            EventFilter(
                mission_id=mission_id,
                after_sequence=after_sequence,
                limit=limit,
            )
        )
        return {
            "mission_id": mission_id,
            "events": [item.model_dump(mode="json") for item in page],
            "next_cursor": page[-1].sequence if page else after_sequence,
        }

    @router.get("/api/runs/{run_id}")
    def run(run_id: str) -> dict[str, Any]:
        payload = pipeline.projector.run(run_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="Run was not found.")
        events = pipeline.events(EventFilter(run_id=run_id, limit=2_000))
        return {
            **payload,
            "events": [item.model_dump(mode="json") for item in events],
        }

    @router.get("/api/metrics/summary")
    def metrics_summary() -> dict[str, Any]:
        return {
            **pipeline.projector.metrics(),
            "stream": pipeline.hub.health(),
            "retained_events": pipeline.store.count(),
        }

    return router


async def _stream_events(
    *,
    request: Request,
    pipeline: ObservabilityPipeline,
    subscription: Any,
    cursor: int,
    limit: int | None,
    mission_id: str | None,
    run_id: str | None,
    severity: Severity | None,
) -> AsyncIterator[str]:
    sent = 0
    last_sent = cursor
    try:
        while True:
            page_limit = min(2_000, limit - sent) if limit is not None else 2_000
            if page_limit <= 0:
                return
            page = pipeline.events(
                EventFilter(
                    after_sequence=last_sent,
                    limit=page_limit,
                    mission_id=mission_id,
                    run_id=run_id,
                    severity=severity,
                )
            )
            if not page:
                break
            for event in page:
                yield _sse_frame(event)
                last_sent = event.sequence or last_sent
                sent += 1
                if limit is not None and sent >= limit:
                    return
            if len(page) < page_limit:
                break

        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(subscription.queue.get(), timeout=12.0)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            if event is None:
                return
            if event.sequence is None or event.sequence <= last_sent:
                continue
            if not _matches(event, mission_id=mission_id, run_id=run_id, severity=severity):
                continue
            yield _sse_frame(event)
            last_sent = event.sequence
            sent += 1
            if limit is not None and sent >= limit:
                return
    finally:
        pipeline.hub.unsubscribe(subscription)


def _matches(
    event: TraceEvent,
    *,
    mission_id: str | None,
    run_id: str | None,
    severity: Severity | None,
) -> bool:
    return (
        (mission_id is None or event.mission_id == mission_id)
        and (run_id is None or event.run_id == run_id)
        and (severity is None or event.severity == severity)
    )


def _sse_frame(event: TraceEvent) -> str:
    payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
    return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"
