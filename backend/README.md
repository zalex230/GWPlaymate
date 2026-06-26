# GWPlaymate Backend

This backend is the first bridge between the GWToolbox++ Playmate plugin, Supabase, and a Mac Mini running Hermes/Ollama.

```text
GWPlaymate.dll -> Windows localhost bridge -> Supabase -> Hermes daemon -> Ollama
```

The C++ plugin still captures local JSONL logs. Cloud credentials live only in these Python services.

## Layout

- `shared/` contains Pydantic models, event names, throttling helpers, and RAM world-state types.
- `windows_bridge/` exposes the plugin-compatible HTTP API on `127.0.0.1:8787`.
- `hermes_daemon/` listens to Supabase Postgres Changes and writes companion replies.
- `supabase/` contains SQL setup/compatibility checks for existing GWPlaymate tables.
- `tests/` covers payload validation, throttling, state updates, and Hermes decision parsing.

## Setup

Create a virtual environment and install pinned dependencies:

```powershell
cd C:\Users\alexz\Documents\Playmate - GWToolbox_Fork
python -m venv .venv-playmate
.\.venv-playmate\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Copy the template and fill in your Supabase values:

```powershell
Copy-Item backend\.env.example backend\.env
```

The Supabase project is `GWPlaymate` / `akijihvbqemiqpbeknnr`.

## Windows Bridge

Run this on the Gaming PC:

```powershell
python -m backend.windows_bridge.app
```

Then in the Playmate plugin:

- `Local backend URL`: `http://127.0.0.1:8787`
- `Write local JSONL capture`: on
- `Send telemetry to backend`: on, after local logs look sane

Smoke test without GW1:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File backend\scripts\smoke-test-bridge.ps1
```

## Hermes Daemon

Run this on the Mac Mini after installing the same requirements:

```bash
python -m backend.hermes_daemon.daemon
```

The daemon listens for `INSERT` events on `public.game_logs` using Supabase Postgres Changes. It keeps recent context in RAM, asks Ollama for a small JSON decision, and inserts approved lines into `companion_replies`.

## Supabase

Run `backend/supabase/setup.sql` in the Supabase SQL editor. It is written to be idempotent and only adds minimal compatibility columns/publication membership needed by this backend.

Keep `service_role` or secret keys out of the plugin and out of git.
