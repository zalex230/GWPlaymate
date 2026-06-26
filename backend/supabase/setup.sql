-- GWPlaymate backend compatibility setup.
-- Run in Supabase SQL Editor after reviewing. This is idempotent.

alter table if exists public.game_logs
    add column if not exists source text not null default 'gwtoolboxpp-playmate',
    add column if not exists event_type text not null default 'game_log',
    add column if not exists map_id integer,
    add column if not exists instance_type integer,
    add column if not exists district integer,
    add column if not exists instance_time integer,
    add column if not exists active_quest_id integer,
    add column if not exists quest_count integer,
    add column if not exists active_quest_name text,
    add column if not exists active_quest_objectives text,
    add column if not exists payload jsonb not null default '{}'::jsonb;

create table if not exists public.companion_replies (
    id bigserial primary key,
    created_at timestamptz not null default now(),
    consumed_at timestamptz,
    persona text not null,
    message text not null,
    channel text not null default 'party',
    payload jsonb not null default '{}'::jsonb
);

alter table if exists public.companion_replies
    add column if not exists consumed_at timestamptz,
    add column if not exists persona text,
    add column if not exists message text,
    add column if not exists channel text not null default 'party',
    add column if not exists payload jsonb not null default '{}'::jsonb;

create table if not exists public.environment_alerts (
    id bigserial primary key,
    created_at timestamptz not null default now(),
    alert_type text not null default 'environment_alert',
    severity text not null default 'NORMAL',
    map_id integer,
    player_x real,
    player_y real,
    agent_id integer,
    model_id integer,
    agent_name text,
    distance real,
    faction text,
    message text,
    payload jsonb not null default '{}'::jsonb
);

alter table if exists public.environment_alerts
    add column if not exists alert_type text not null default 'environment_alert',
    add column if not exists severity text not null default 'NORMAL',
    add column if not exists map_id integer,
    add column if not exists message text,
    add column if not exists payload jsonb not null default '{}'::jsonb;

alter table public.companion_replies enable row level security;
alter table public.environment_alerts enable row level security;

do $$
begin
    if not exists (
        select 1
        from pg_publication
        where pubname = 'supabase_realtime'
    ) then
        create publication supabase_realtime;
    end if;

    if not exists (
        select 1
        from pg_publication_tables
        where pubname = 'supabase_realtime'
          and schemaname = 'public'
          and tablename = 'game_logs'
    ) then
        alter publication supabase_realtime add table public.game_logs;
    end if;

    if not exists (
        select 1
        from pg_publication_tables
        where pubname = 'supabase_realtime'
          and schemaname = 'public'
          and tablename = 'companion_replies'
    ) then
        alter publication supabase_realtime add table public.companion_replies;
    end if;

    if not exists (
        select 1
        from pg_publication_tables
        where pubname = 'supabase_realtime'
          and schemaname = 'public'
          and tablename = 'environment_alerts'
    ) then
        alter publication supabase_realtime add table public.environment_alerts;
    end if;
end $$;
