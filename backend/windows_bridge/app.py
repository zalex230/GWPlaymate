from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException

from backend.shared.config import load_settings
from backend.shared.constants import (
    COMPANION_REPLIES_TABLE,
    ENVIRONMENT_ALERTS_TABLE,
    ENVIRONMENT_EVENT_TYPES,
    GAME_LOGS_TABLE,
    NOISY_CHANNELS,
)
from backend.shared.models import CompanionReplyRow, RepliesResponse, TelemetryEvent
from backend.shared.supabase_client import create_supabase_client
from backend.shared.throttle import EventThrottle


settings = load_settings()
app = FastAPI(title="GWPlaymate Windows Bridge", version="0.1.0")
throttle = EventThrottle(settings.snapshot_min_interval_seconds)


def _client():
    return create_supabase_client(settings)


def _insert_event(event: TelemetryEvent) -> dict[str, Any]:
    client = _client()
    if event.channel in NOISY_CHANNELS:
        return {"accepted": False, "reason": "noisy_channel"}
    if not throttle.should_accept(event):
        return {"accepted": False, "reason": "throttled"}

    if event.event_type in ENVIRONMENT_EVENT_TYPES:
        client.table(ENVIRONMENT_ALERTS_TABLE).insert(event.to_environment_alert_insert()).execute()
    else:
        client.table(GAME_LOGS_TABLE).insert(event.to_game_log_insert()).execute()
    return {"accepted": True}


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "gwplaymate-windows-bridge",
        "supabase_project": "akijihvbqemiqpbeknnr",
    }


@app.post("/v1/playmate/events")
def post_event(event: TelemetryEvent) -> dict[str, Any]:
    try:
        return _insert_event(event)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/playmate/replies", response_model=RepliesResponse)
def get_replies(persona: str | None = None, session_id: str | None = None, limit: int | None = None) -> RepliesResponse:
    client = _client()
    query = (
        client.table(COMPANION_REPLIES_TABLE)
        .select("*")
        .is_("consumed_at", "null")
        .order("created_at", desc=False)
        .limit(limit or settings.reply_limit)
    )
    if persona:
        query = query.eq("persona", persona)

    try:
        response = query.execute()
        rows = [CompanionReplyRow.model_validate(row) for row in response.data or []]
        if session_id:
            rows = [row for row in rows if row.payload_session_id() == session_id]
        if rows:
            consumed_at = datetime.now(timezone.utc).isoformat()
            ids = [row.id for row in rows]
            client.table(COMPANION_REPLIES_TABLE).update({"consumed_at": consumed_at}).in_("id", ids).execute()
        return RepliesResponse(replies=[row.message for row in rows])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def main() -> None:
    uvicorn.run("backend.windows_bridge.app:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
