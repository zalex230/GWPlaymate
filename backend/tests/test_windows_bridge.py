from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.windows_bridge.app import _drain_direct_replies, _enqueue_direct_reply, app


class _FakeTable:
    def insert(self, _payload):
        return self

    def execute(self):
        return type("Response", (), {"data": []})()


class _FakeSupabase:
    def table(self, _name):
        return _FakeTable()


class WindowsBridgeTests(unittest.TestCase):
    def test_health(self) -> None:
        client = TestClient(app)

        response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_post_event_accepts_plugin_payload(self) -> None:
        client = TestClient(app)
        payload = {
            "source": "gwtoolboxpp-playmate",
            "persona": "A Test",
            "client_time": "2026-06-26T12:00:00Z",
            "event_type": "player_chat",
            "sender": "Player",
            "channel": "party",
            "message": "hello",
        }

        with patch("backend.windows_bridge.app._client", return_value=_FakeSupabase()):
            response = client.post("/v1/playmate/events", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"accepted": True})

    def test_direct_replies_are_returned_before_supabase_poll(self) -> None:
        client = TestClient(app)

        _enqueue_direct_reply("A Test", "local-playtest", "Direct hello.")

        response = client.get(
            "/v1/playmate/replies",
            params={"persona": "A Test", "session_id": "local-playtest", "limit": 1},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"replies": ["Direct hello."]})

    def test_direct_reply_queue_keeps_other_personas(self) -> None:
        _enqueue_direct_reply("Other", "local-playtest", "Not yours.")

        self.assertEqual(_drain_direct_replies("A Test", "local-playtest", 8), [])
        self.assertEqual(_drain_direct_replies("Other", "local-playtest", 8), ["Not yours."])

    def test_post_event_suppresses_noisy_quest_details(self) -> None:
        client = TestClient(app)
        payload = {
            "source": "gwtoolboxpp-playmate",
            "persona": "A Test",
            "client_time": "2026-06-26T12:00:00Z",
            "event_type": "quest_details_changed",
            "sender": "System",
            "channel": "system",
            "message": "quest_details_changed",
        }

        response = client.post("/v1/playmate/events", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"accepted": False, "reason": "suppressed_event_type"})

    def test_post_event_accepts_control_char_in_quest_payload(self) -> None:
        client = TestClient(app)
        payload = (
            '{"source":"gwtoolboxpp-playmate","persona":"A Test",'
            '"client_time":"2026-06-26T12:00:00Z","event_type":"player_chat",'
            '"sender":"Player","channel":"party","message":"hello",'
            '"active_quest_objectives":"encoded\u0001quest"}'
        )

        with patch("backend.windows_bridge.app._client", return_value=_FakeSupabase()):
            response = client.post(
                "/v1/playmate/events",
                content=payload.encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"accepted": True})

    def test_post_event_routes_environment_alert(self) -> None:
        client = TestClient(app)
        payload = {
            "source": "gwtoolboxpp-playmate",
            "persona": "A Test",
            "client_time": "2026-06-26T12:00:00Z",
            "event_type": "environment_alert",
            "sender": "System",
            "channel": "system",
            "message": "Enemy nearby.",
            "alert_type": "enemy_patrol_nearby",
            "severity": "NORMAL",
            "map_id": 148,
            "hostile_count": 2,
            "close_hostile_count": 1,
        }

        with patch("backend.windows_bridge.app._client", return_value=_FakeSupabase()):
            response = client.post("/v1/playmate/events", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"accepted": True})


if __name__ == "__main__":
    unittest.main()
