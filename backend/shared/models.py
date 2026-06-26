from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    source: str = "gwtoolboxpp-playmate"
    persona: str = "Unknown Character"
    client_time: str | None = None
    event_type: str
    sender: str
    channel: str
    message: str
    map_id: int = 0
    instance_type: int = 0
    district: int = 0
    instance_time: int = 0
    active_quest_id: int = 0
    quest_count: int = 0
    active_quest_name: str = ""
    active_quest_objectives: str = ""
    session_id: str = "local-playtest"

    @field_validator("event_type", "sender", "channel", "message")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value:
            raise ValueError("value must not be empty")
        return value

    @field_validator("channel", mode="before")
    @classmethod
    def normalize_channel(cls, value: Any) -> str:
        return str(value).strip().lower()

    @field_validator("event_type", mode="before")
    @classmethod
    def normalize_event_type(cls, value: Any) -> str:
        return str(value).strip().lower()

    def metadata(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "persona": self.persona,
            "client_time": self.client_time,
            "event_type": self.event_type,
            "map_id": self.map_id,
            "instance_type": self.instance_type,
            "district": self.district,
            "instance_time": self.instance_time,
            "active_quest_id": self.active_quest_id,
            "quest_count": self.quest_count,
            "active_quest_name": self.active_quest_name,
            "active_quest_objectives": self.active_quest_objectives,
            "session_id": self.session_id,
        }

    def to_game_log_insert(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "event_type": self.event_type,
            "sender": self.sender,
            "message": self.message,
            "channel": self.channel,
            "map_id": self.map_id,
            "instance_type": self.instance_type,
            "district": self.district,
            "instance_time": self.instance_time,
            "active_quest_id": self.active_quest_id,
            "quest_count": self.quest_count,
            "active_quest_name": self.active_quest_name,
            "active_quest_objectives": self.active_quest_objectives,
            "payload": self.metadata(),
        }

    def to_environment_alert_insert(self) -> dict[str, Any]:
        metadata = self.metadata()
        return {
            "alert_type": self.event_type,
            "severity": str(metadata.get("severity") or "NORMAL"),
            "map_id": self.map_id or None,
            "message": self.message,
            "payload": metadata,
        }


class CompanionReplyInsert(BaseModel):
    persona: str
    message: str
    channel: str = "party"
    session_id: str = "local-playtest"
    urgency: str = "NORMAL"
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_supabase_insert(self) -> dict[str, Any]:
        return {
            "persona": self.persona,
            "message": self.message,
            "channel": self.channel,
            "payload": {
                "session_id": self.session_id,
                "urgency": self.urgency,
                **self.metadata,
            },
        }


class CompanionReplyRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    persona: str | None = None
    message: str
    channel: str = "party"
    session_id: str | None = None
    urgency: str | None = None
    consumed_at: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def payload_session_id(self) -> str | None:
        return self.session_id or self.payload.get("session_id")


class RepliesResponse(BaseModel):
    replies: list[str] = Field(default_factory=list)


class HermesDecision(BaseModel):
    should_speak: bool = False
    channel_override: Literal["CHANNEL_PARTY", "CHANNEL_LOCAL", "CHANNEL_SYSTEM"] = "CHANNEL_LOCAL"
    urgency: Literal["LOW", "NORMAL", "HIGH"] = "NORMAL"
    response: str = ""

    @field_validator("response")
    @classmethod
    def trim_response(cls, value: str) -> str:
        return value.strip()

    def to_reply(self, persona: str, session_id: str) -> CompanionReplyInsert | None:
        if not self.should_speak or not self.response:
            return None
        channel_map = {
            "CHANNEL_PARTY": "party",
            "CHANNEL_LOCAL": "local",
            "CHANNEL_SYSTEM": "system",
        }
        return CompanionReplyInsert(
            persona=persona,
            message=self.response,
            channel=channel_map[self.channel_override],
            session_id=session_id,
            urgency=self.urgency,
            metadata={"channel_override": self.channel_override},
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
