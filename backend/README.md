# GWPlaymate Backend

This backend is the first bridge between the GWToolbox++ Playmate plugin, a LAN Hermes/Ollama service, and Supabase audit/memory storage.

```text
GWPlaymate.dll -> Windows localhost bridge -> Hermes daemon -> Ollama
                                      \-> Supabase audit/memory storage
```

The C++ plugin still captures local JSONL logs. Cloud credentials live only in these Python services.

## Layout

- `shared/` contains Pydantic models, event names, throttling helpers, and RAM world-state types.
- `windows_bridge/` exposes the plugin-compatible HTTP API on `127.0.0.1:8787`.
- `hermes_daemon/` exposes a LAN HTTP API for low-latency replies and can also listen to Supabase Postgres Changes.
- `supabase/` contains SQL setup/compatibility checks for existing GWPlaymate tables.
- `tests/` covers payload validation, throttling, state updates, and Hermes decision parsing.

## Setup

Create a virtual environment and install pinned dependencies:

```powershell
cd C:\dev\GWPlaymate
python -m venv .venv-playmate
.\.venv-playmate\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Copy the template and fill in your Supabase values:

```powershell
Copy-Item backend\.env.example backend\.env
```

Use your own Supabase project URL and keys in `backend/.env`. For example,
`SUPABASE_URL=https://your-project-ref.supabase.co`.

Use the `service_role` key only in `backend/.env` on trusted machines. Do not put Supabase keys in the
GWToolbox plugin UI, the DLL, or committed files.

## Windows Bridge

Run this on the Gaming PC:

```powershell
python -m backend.windows_bridge.app
```

For low-latency replies, point the bridge at the Mac Mini Hermes service:

```env
HERMES_DIRECT_URL=http://mac-mini-hostname-or-ip:8797
```

Then in the Playmate plugin:

- `Local backend URL`: `http://127.0.0.1:8787`
- `Write local JSONL capture`: on
- `Send telemetry to backend`: on, after local logs look sane

The bridge rejects known noisy event types locally, forwards accepted `player_chat` and
`environment_alert` events to Hermes in the background, and writes accepted events to Supabase as an
audit trail. Supabase is not on the critical reply path. For v1 this suppresses `quest_added` and
`quest_details_changed` until quest text decoding and de-duplication are fixed.
Audit rows that were already sent over the direct LAN path are marked so Hermes Realtime will not
generate duplicate replies from them.

Smoke test without GW1:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File backend\scripts\smoke-test-bridge.ps1
```

## Hermes Daemon

Run this on the Mac Mini after installing the same requirements:

```bash
python -m backend.hermes_daemon.daemon
```

The daemon exposes `POST /v1/hermes/events` and `GET /health` on `HERMES_HOST:HERMES_PORT`.
Set `HERMES_HOST=0.0.0.0` on the Mac Mini if the Windows bridge should reach it over your LAN.

The daemon keeps recent context in RAM, asks Ollama for a small JSON decision, and returns approved
lines directly to the Windows bridge. If `HERMES_AUDIT_REPLIES=true`, direct replies are also inserted
into `companion_replies` with `consumed_at` set so they are traceable but not delivered twice.

If `HERMES_ENABLE_REALTIME=true`, the daemon also listens for `INSERT` events on `public.game_logs`
and `public.environment_alerts` using Supabase Postgres Changes for audit/backfill compatibility.

For the first closed-loop test, leave `HERMES_USE_OLLAMA=false`. In this fallback mode Hermes replies
deterministically to party `player_chat` rows, which proves the Supabase round trip without involving
model setup. Set `HERMES_USE_OLLAMA=true` when the pipe is proven and Ollama is ready on the Mac Mini.

Replies are written to `companion_replies`, not back into `game_logs`, and include `trigger_log_id`
when the source Supabase row is available.

## Closed-loop smoke test

1. Start the Mac Mini Hermes daemon with `HERMES_USE_OLLAMA=false`.
2. Start the Windows bridge with `HERMES_DIRECT_URL` pointing to Hermes.
3. From the Windows PC, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File backend\scripts\smoke-test-bridge.ps1
```

Expected result:

- the bridge returns `{ "accepted": true }` for the synthetic `player_chat`;
- Supabase receives one `game_logs` row;
- Hermes returns one direct reply to the bridge;
- the bridge returns that reply once from `GET /v1/playmate/replies`;
- Supabase receives audit rows for the accepted event and, when enabled, the generated reply.

After that passes, run the same loop from GW1 by enabling `Send telemetry to backend` and `Inject
companion replies into party chat` in the Playmate panel.

## Proactive radar

The plugin can emit `environment_alert` telemetry while in explorable areas. V1 alerts are transition
based rather than continuous spam:

- `enemy_patrol_nearby` when a living enemy enters close range;
- `combat_started` when combat-like state begins;
- `danger_spike` when several enemies are close;
- `combat_over` when combat clears.

These alerts are forwarded directly to Hermes and stored in `environment_alerts` for audit/memory.

## Supabase

Run `backend/supabase/setup.sql` in the Supabase SQL editor. It is written to be idempotent and only adds minimal compatibility columns/publication membership needed by this backend.

Keep `service_role` or secret keys out of the plugin and out of git.
