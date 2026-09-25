-- career-intel-engine core tables (apply in Supabase SQL editor if empty)
create extension if not exists pgcrypto;

create table if not exists public.companies (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  job_number serial unique,
  company_id uuid references public.companies(id) on delete set null,
  title text not null,
  company_name text not null,
  url text not null unique,
  description text,
  archetype text,
  ats_system text,
  status text not null default 'New',
  score_band text,
  score integer,
  cv_path text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.jobs
  add column if not exists updated_at timestamptz not null default now();

alter table public.jobs
  add column if not exists job_number serial;

create unique index if not exists jobs_job_number_uidx on public.jobs (job_number);

create table if not exists public.applications (
  id uuid primary key default gen_random_uuid(),
  job_id uuid references public.jobs(id) on delete cascade,
  status text not null default 'draft',
  cv_path text,
  created_at timestamptz not null default now()
);

create table if not exists public.interviews (
  id uuid primary key default gen_random_uuid(),
  application_id uuid references public.applications(id) on delete cascade,
  scheduled_at timestamptz,
  stage text,
  notes text,
  created_at timestamptz not null default now()
);

alter table public.companies enable row level security;
alter table public.jobs enable row level security;
alter table public.applications enable row level security;
alter table public.interviews enable row level security;

create index if not exists jobs_url_idx on public.jobs (url);
create index if not exists jobs_status_idx on public.jobs (status);
