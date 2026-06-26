from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import ollama
from supabase import acreate_client

from backend.shared.config import load_settings
from backend.shared.constants import COMPANION_REPLIES_TABLE, GAME_LOGS_TABLE
from backend.shared.models import CompanionReplyInsert, HermesDecision, TelemetryEvent
from backend.shared.state import LiveWorldState
from backend.shared.supabase_client import create_supabase_client


settings = load_settings()
world_state = LiveWorldState(
    recent_chat_limit=settings.recent_chat_limit,
    recent_alert_limit=settings.recent_alert_limit,
    session_id=settings.active_session,
)


def event_from_game_log(record: dict[str, Any]) -> TelemetryEvent:
    metadata = record.get("payload") or record.get("metadata") or {}
    return TelemetryEvent(
        source=record.get("source") or metadata.get("source", "supabase-game-log"),
        persona=metadata.get("persona", record.get("sender") or "Unknown Character"),
        client_time=metadata.get("client_time"),
        event_type=record.get("event_type") or metadata.get("event_type", "game_log"),
        sender=record.get("sender") or "Game",
        channel=record.get("channel") or "system",
        message=record.get("message") or "",
        map_id=record.get("map_id") or metadata.get("map_id", 0),
        instance_type=record.get("instance_type") or metadata.get("instance_type", 0),
        district=record.get("district") or metadata.get("district", 0),
        instance_time=record.get("instance_time") or metadata.get("instance_time", 0),
        active_quest_id=record.get("active_quest_id") or metadata.get("active_quest_id", 0),
        quest_count=record.get("quest_count") or metadata.get("quest_count", 0),
        active_quest_name=record.get("active_quest_name") or metadata.get("active_quest_name", ""),
        active_quest_objectives=record.get("active_quest_objectives") or metadata.get("active_quest_objectives", ""),
        session_id=metadata.get("session_id", settings.active_session),
    )


def extract_json_object(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def build_decision_prompt(event: TelemetryEvent) -> str:
    return (
        "You are the Playmate companion speech gate for Guild Wars 1.\n"
        "Decide whether the companion should speak in-game now.\n"
        "Return exactly one JSON object with keys: should_speak, channel_override, urgency, response.\n"
        "Valid channel_override values: CHANNEL_PARTY, CHANNEL_LOCAL, CHANNEL_SYSTEM.\n"
        "Use CHANNEL_PARTY only for direct player interaction or high urgency danger.\n"
        "Stay concise and in-character. If unsure, set should_speak false.\n\n"
        f"Incoming event: {event.model_dump_json()}\n\n"
        f"Live world state:\n{world_state.prompt_context()}"
    )


def decide_with_ollama(event: TelemetryEvent) -> HermesDecision:
    prompt = build_decision_prompt(event)
    response = ollama.generate(
        model=settings.ollama_model,
        prompt=prompt,
        options={"temperature": 0.3},
    )
    raw = response.get("response", "{}")
    return HermesDecision.model_validate(extract_json_object(raw))


def fallback_rule_decision(event: TelemetryEvent) -> HermesDecision:
    if event.event_type == "player_chat" and event.channel == "party":
        return HermesDecision(
            should_speak=True,
            channel_override="CHANNEL_PARTY",
            urgency="NORMAL",
            response="I'm here. I caught that.",
        )
    if event.event_type == "environment_alert":
        return HermesDecision(
            should_speak=True,
            channel_override="CHANNEL_PARTY",
            urgency="HIGH",
            response="Careful. Something nearby looks dangerous.",
        )
    return HermesDecision(should_speak=False)


def insert_reply(reply: CompanionReplyInsert) -> None:
    client = create_supabase_client(settings)
    client.table(COMPANION_REPLIES_TABLE).insert(reply.to_supabase_insert()).execute()


async def handle_game_log_payload(payload: dict[str, Any], *, use_ollama: bool = True) -> None:
    record = payload.get("record") or payload
    event = event_from_game_log(record)
    world_state.apply_event(event)

    if not world_state.can_speak(settings.hermes_min_speak_seconds):
        return

    decision = decide_with_ollama(event) if use_ollama else fallback_rule_decision(event)
    reply = decision.to_reply(persona=world_state.persona, session_id=world_state.session_id)
    if not reply:
        return

    insert_reply(reply)
    world_state.mark_spoken()


async def subscribe_to_game_logs() -> None:
    if not settings.supabase_url:
        raise RuntimeError("SUPABASE_URL is required")
    if not settings.supabase_service_key:
        raise RuntimeError("SUPABASE_SERVICE_KEY is required")

    client = await acreate_client(settings.supabase_url, settings.supabase_service_key)
    channel = client.channel("gwplaymate-game-logs")
    channel.on_postgres_changes(
        "INSERT",
        callback=lambda payload: asyncio.create_task(handle_game_log_payload(payload)),
        table=GAME_LOGS_TABLE,
        schema="public",
    )
    await channel.subscribe()


async def main_async() -> None:
    await subscribe_to_game_logs()
    print("GWPlaymate Hermes daemon listening for Supabase game_logs inserts.")
    while True:
        await asyncio.sleep(1)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
