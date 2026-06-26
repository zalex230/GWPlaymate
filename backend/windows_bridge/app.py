from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from json import JSONDecodeError
from threading import Lock
from typing import Any

import httpx
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import ValidationError

from backend.shared.config import load_settings
from backend.shared.constants import (
    COMPANION_REPLIES_TABLE,
    DIRECT_HERMES_EVENT_TYPES,
    ENVIRONMENT_ALERTS_TABLE,
    ENVIRONMENT_EVENT_TYPES,
    GAME_LOGS_TABLE,
    NOISY_CHANNELS,
    SUPPRESSED_EVENT_TYPES,
)
from backend.shared.models import CompanionReplyRow, HermesEventResponse, RepliesResponse, TelemetryEvent
from backend.shared.supabase_client import create_supabase_client, require_supabase_settings
from backend.shared.throttle import EventThrottle


settings = load_settings()
app = FastAPI(title="GWPlaymate Windows Bridge", version="0.1.0")
throttle = EventThrottle(settings.snapshot_min_interval_seconds)


@dataclass(frozen=True)
class LocalReply:
    persona: str
    session_id: str
    message: str


_direct_replies: deque[LocalReply] = deque(maxlen=128)
_direct_replies_lock = Lock()


def _client():
    return create_supabase_client(settings)


def _accept_event(event: TelemetryEvent) -> dict[str, Any]:
    if event.channel in NOISY_CHANNELS:
        return {"accepted": False, "reason": "noisy_channel"}
    if event.event_type in SUPPRESSED_EVENT_TYPES:
        return {"accepted": False, "reason": "suppressed_event_type"}
    if not throttle.should_accept(event):
        return {"accepted": False, "reason": "throttled"}
    return {"accepted": True}


def _audit_event(event: TelemetryEvent, *, direct_forwarded: bool = False) -> None:
    try:
        client = _client()
        if event.event_type in ENVIRONMENT_EVENT_TYPES:
            row = event.to_environment_alert_insert()
            if direct_forwarded:
                row["payload"]["delivery_path"] = "direct_lan"
                row["payload"]["direct_hermes_forwarded"] = True
            client.table(ENVIRONMENT_ALERTS_TABLE).insert(row).execute()
        else:
            row = event.to_game_log_insert()
            if direct_forwarded:
                row["payload"]["delivery_path"] = "direct_lan"
                row["payload"]["direct_hermes_forwarded"] = True
            client.table(GAME_LOGS_TABLE).insert(row).execute()
    except Exception as exc:
        print(f"Supabase audit insert failed: {exc}")


def _hermes_direct_url() -> str:
    return settings.hermes_direct_url.rstrip("/")


def _should_forward_to_hermes(event: TelemetryEvent) -> bool:
    return bool(_hermes_direct_url()) and event.event_type in DIRECT_HERMES_EVENT_TYPES


def _enqueue_direct_reply(persona: str, session_id: str, message: str) -> None:
    if not message:
        return
    with _direct_replies_lock:
        _direct_replies.append(LocalReply(persona=persona, session_id=session_id, message=message))


def _drain_direct_replies(persona: str | None, session_id: str | None, limit: int) -> list[str]:
    replies: list[str] = []
    kept: deque[LocalReply] = deque(maxlen=128)
    with _direct_replies_lock:
        while _direct_replies:
            reply = _direct_replies.popleft()
            if len(replies) < limit and (not persona or reply.persona == persona) and (
                not session_id or reply.session_id == session_id
            ):
                replies.append(reply.message)
            else:
                kept.append(reply)
        _direct_replies.extend(kept)
    return replies


def _forward_to_hermes(event: TelemetryEvent) -> None:
    url = f"{_hermes_direct_url()}/v1/hermes/events"
    try:
        response = httpx.post(
            url,
            json=event.model_dump(mode="json"),
            timeout=settings.hermes_direct_timeout_seconds,
        )
        response.raise_for_status()
        hermes_response = HermesEventResponse.model_validate(response.json())
    except Exception as exc:
        print(f"Direct Hermes forward failed: {exc}")
        return

    for reply in hermes_response.replies:
        _enqueue_direct_reply(event.persona, event.session_id, reply)


def _strip_invalid_json_control_chars(text: str) -> str:
    return "".join(ch for ch in text if ch in "\t\n\r" or ord(ch) >= 0x20)


async def _event_from_request(request: Request) -> TelemetryEvent:
    raw = await request.body()
    text = raw.decode("utf-8", errors="replace")
    text = _strip_invalid_json_control_chars(text)
    try:
        payload = json.loads(text)
    except JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid telemetry JSON: {exc.msg}") from exc
    try:
        return TelemetryEvent.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "gwplaymate-windows-bridge",
        "supabase_configured": bool(settings.supabase_url and settings.supabase_service_key),
        "direct_hermes_configured": bool(_hermes_direct_url()),
    }


@app.post("/v1/playmate/events")
async def post_event(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        event = await _event_from_request(request)
        result = _accept_event(event)
        direct_forwarded = result.get("accepted") and _should_forward_to_hermes(event)
        if direct_forwarded:
            background_tasks.add_task(_forward_to_hermes, event)
        if result.get("accepted"):
            background_tasks.add_task(_audit_event, event, direct_forwarded=direct_forwarded)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        if local_replies:
            return RepliesResponse(replies=local_replies)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/v1/playmate/replies", response_model=RepliesResponse)
def get_replies(persona: str | None = None, session_id: str | None = None, limit: int | None = None) -> RepliesResponse:
    reply_limit = limit or settings.reply_limit
    local_replies = _drain_direct_replies(persona, session_id, reply_limit)
    if len(local_replies) >= reply_limit:
        return RepliesResponse(replies=local_replies)

    client = _client()
    query = (
        client.table(COMPANION_REPLIES_TABLE)
        .select("*")
        .is_("consumed_at", "null")
        .order("created_at", desc=False)
        .limit(reply_limit - len(local_replies))
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
        return RepliesResponse(replies=[*local_replies, *[row.message for row in rows]])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def main() -> None:
    require_supabase_settings(settings)
    uvicorn.run("backend.windows_bridge.app:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
