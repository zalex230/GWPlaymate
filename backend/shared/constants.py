from __future__ import annotations

CHAT_EVENT_TYPES = {"player_chat", "chat_log"}
SNAPSHOT_EVENT_TYPES = {
    "plugin_started",
    "snapshot",
    "map_changed",
    "active_quest_changed",
    "map_loaded",
    "map_change",
    "quest_added",
    "quest_details_changed",
}
ENVIRONMENT_EVENT_TYPES = {"environment_alert"}

CHAT_CHANNELS = {"party", "local", "guild", "alliance", "whisper", "system", "warning", "emote"}
NOISY_CHANNELS = {"trade"}
SUPPRESSED_EVENT_TYPES = {"quest_added", "quest_details_changed"}

GAME_LOGS_TABLE = "game_logs"
ENVIRONMENT_ALERTS_TABLE = "environment_alerts"
COMPANION_REPLIES_TABLE = "companion_replies"

DEFAULT_SESSION_ID = "local-playtest"
