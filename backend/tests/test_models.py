from __future__ import annotations

import unittest

from pydantic import ValidationError

from backend.shared.models import HermesDecision, TelemetryEvent


class ModelTests(unittest.TestCase):
    def test_telemetry_normalizes_channel_and_event_type(self) -> None:
        event = TelemetryEvent(
            persona="A Test",
            event_type=" Player_Chat ",
            sender="Player",
            channel=" Party ",
            message="hello",
        )

        self.assertEqual(event.event_type, "player_chat")
        self.assertEqual(event.channel, "party")
        self.assertEqual(event.to_game_log_insert()["payload"]["persona"], "A Test")

    def test_telemetry_requires_message(self) -> None:
        with self.assertRaises(ValidationError):
            TelemetryEvent(event_type="player_chat", sender="Player", channel="party", message="")

    def test_hermes_decision_to_reply(self) -> None:
        decision = HermesDecision(
            should_speak=True,
            channel_override="CHANNEL_PARTY",
            urgency="HIGH",
            response="Hold up.",
        )

        reply = decision.to_reply("A Test", "session")

        self.assertIsNotNone(reply)
        self.assertEqual(reply.channel, "party")
        self.assertEqual(reply.urgency, "HIGH")

    def test_reply_insert_includes_trigger_log_id(self) -> None:
        decision = HermesDecision(
            should_speak=True,
            channel_override="CHANNEL_PARTY",
            response="Hold up.",
        )

        row = decision.to_reply("A Test", "session", trigger_log_id=7).to_supabase_insert()

        self.assertEqual(row["trigger_log_id"], 7)
        self.assertEqual(row["payload"]["trigger_log_id"], 7)

    def test_environment_alert_insert_maps_radar_fields(self) -> None:
        event = TelemetryEvent(
            persona="A Test",
            event_type="environment_alert",
            sender="System",
            channel="system",
            message="Enemy nearby.",
            alert_type="enemy_patrol_nearby",
            severity="HIGH",
            map_id=148,
            player_x=10,
            player_y=20,
            hostile_count=3,
            close_hostile_count=2,
            closest_hostile_agent_id=99,
            closest_hostile_distance=1234.5,
        )

        row = event.to_environment_alert_insert()

        self.assertEqual(row["alert_type"], "enemy_patrol_nearby")
        self.assertEqual(row["severity"], "HIGH")
        self.assertEqual(row["agent_id"], 99)
        self.assertEqual(row["distance"], 1234.5)
        self.assertEqual(row["payload"]["close_hostile_count"], 2)


if __name__ == "__main__":
    unittest.main()
