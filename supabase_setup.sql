-- Staff table
create table if not exists staff (
  id bigint generated always as identity primary key,
  name text not null,
  token text not null unique,
  fcm_token text,
  created_at timestamptz default now()
);

-- Messages table
create table if not exists messages (
  id bigint generated always as identity primary key,
  title text not null default 'Staff Update',
  body text not null,
  target text not null default 'all',
  created_at timestamptz default now()
);

-- Disable RLS (backend handles auth)
alter table staff disable row level security;
alter table messages disable row level security;
