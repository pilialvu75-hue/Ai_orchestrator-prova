-- AIrLab Memory Fabric V1 reference schema.
-- This is intentionally a schema source, not a generated Supabase migration.
-- When a Supabase project is available, create the real migration with the
-- Supabase CLI/MCP workflow, apply it, run advisors, and verify with queries.

create table if not exists public.airlab_memory_records (
    id uuid primary key,
    namespace text not null,
    type text not null,
    subject text not null,
    content text not null default '',
    structured_data jsonb not null default '{}'::jsonb,
    source text not null,
    confidence double precision not null default 1.0
        check (confidence >= 0.0 and confidence <= 1.0),
    created_at timestamptz not null,
    updated_at timestamptz not null,
    version integer not null default 1 check (version >= 1),
    ttl bigint null check (ttl is null or ttl >= 0),
    replication_state jsonb not null default '{}'::jsonb,
    privacy_level text not null
        check (privacy_level in ('public', 'project', 'private', 'device_only', 'secret')),
    checksum text not null,
    tags text[] not null default '{}',
    project_id text null,
    user_id text null,
    agent_id text null,
    conversation_id text null
);

create index if not exists airlab_memory_namespace_idx
    on public.airlab_memory_records (namespace);

create index if not exists airlab_memory_type_idx
    on public.airlab_memory_records (type);

create index if not exists airlab_memory_project_idx
    on public.airlab_memory_records (project_id)
    where project_id is not null;

create index if not exists airlab_memory_user_idx
    on public.airlab_memory_records (user_id)
    where user_id is not null;

create index if not exists airlab_memory_agent_idx
    on public.airlab_memory_records (agent_id)
    where agent_id is not null;

create index if not exists airlab_memory_updated_idx
    on public.airlab_memory_records (updated_at desc);

create index if not exists airlab_memory_tags_gin_idx
    on public.airlab_memory_records using gin (tags);

create or replace function public.airlab_memory_guard_version()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if new.version < old.version then
        raise exception 'memory version regression: % < %', new.version, old.version;
    end if;

    if new.version = old.version and new.checksum <> old.checksum then
        raise exception 'same-version memory checksum conflict for %', new.id;
    end if;

    return new;
end;
$$;

drop trigger if exists airlab_memory_version_guard
    on public.airlab_memory_records;

create trigger airlab_memory_version_guard
before update on public.airlab_memory_records
for each row execute function public.airlab_memory_guard_version();

-- The V1 adapter is a trusted backend adapter. Mobile/browser clients must not
-- receive a Supabase secret/service-role key.
alter table public.airlab_memory_records enable row level security;

revoke all on table public.airlab_memory_records from anon, authenticated;
grant select, insert, update, delete
    on table public.airlab_memory_records to service_role;

revoke all on function public.airlab_memory_guard_version()
    from public, anon, authenticated;
grant execute on function public.airlab_memory_guard_version()
    to service_role;
