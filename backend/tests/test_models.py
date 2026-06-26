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


if __name__ == "__main__":
    unittest.main()
