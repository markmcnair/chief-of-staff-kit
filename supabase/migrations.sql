-- Outbound message queue for the iMessage bridge.
-- Grok Bot inserts rows as 'pending'; ONLY the owner's explicit approval flips them to 'approved'.
-- The Mac bridge can only see/claim 'approved' rows (via the bridge-outbox edge function).
create schema if not exists bridge;

create table if not exists bridge.outbox (
  id           bigint generated always as identity primary key,
  handle       text not null,                 -- phone/email handle as it appears in Messages
  body         text not null,
  service      text not null default 'iMessage' check (service in ('iMessage','SMS')),
  status       text not null default 'pending'
               check (status in ('pending','approved','claimed','sent','failed','cancelled')),
  approved_at  timestamptz,
  claimed_at   timestamptz,
  finished_at  timestamptz,
  error        text,
  created_at   timestamptz not null default now()
);
create index if not exists outbox_status_idx on bridge.outbox(status, id);

-- No anon/authenticated access; only the service role (edge function) touches it.
alter table bridge.outbox enable row level security;
revoke all on bridge.outbox from anon, authenticated;
grant usage on schema bridge to service_role;
grant all on bridge.outbox to service_role;

-- Atomic claim so two bridge runs can never send the same row twice.
create or replace function bridge.claim_outbox(p_id bigint)
returns setof bridge.outbox language sql security definer set search_path = bridge as $$
  update bridge.outbox set status = 'claimed', claimed_at = now()
   where id = p_id and status = 'approved'
  returning *;
$$;
revoke all on function bridge.claim_outbox(bigint) from public, anon, authenticated;
grant execute on function bridge.claim_outbox(bigint) to service_role;
-- Remember to add "bridge" to Settings > API > Exposed schemas so the edge function can reach it.
