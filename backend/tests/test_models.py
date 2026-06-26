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


if __name__ == "__main__":
    unittest.main()
