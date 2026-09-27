create table if not exists books (
  id uuid primary key default gen_random_uuid(),
  title text,
  author text,
  description text,
  cover_url text,
  total_chapters int,
  created_at timestamptz default now()
);

create table if not exists episodes (
  id uuid primary key default gen_random_uuid(),
  book_id uuid references books(id) on delete cascade,
  episode_number int,
  title text,
  duration int,
  audio_url text,
  created_at timestamptz default now()
);

create unique index if not exists episodes_book_number_uidx
  on episodes (book_id, episode_number);

insert into storage.buckets (id, name, public)
values ('audiobooks', 'audiobooks', true)
on conflict (id) do update set public = true;

drop policy if exists "Public read access" on storage.objects;

create policy "Public read access"
  on storage.objects for select
  using (bucket_id = 'audiobooks');
