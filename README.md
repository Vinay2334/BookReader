# BookReader — PDF-to-Audiobook Platform

## Structure

- `backend/` — FastAPI API (routers, Pydantic schemas, async handlers)
- `frontend/` — Next.js App Router + TypeScript + Tailwind CSS
- `supabase/schema.sql` — Database + storage setup

## 1. Supabase setup

1. Run `supabase/schema.sql` in the Supabase SQL Editor (creates `books`,
   `episodes`, and the public `audiobooks` bucket).
2. Confirm the `audiobooks` bucket is public under Storage.
3. Copy `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from Project Settings → API.

## 2. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # fill in SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/health`

### Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/books/extract` | Multipart PDF upload → background job: all pages extracted, chapters segmented in token-budgeted windows |
| GET | `/api/books/extract/jobs/{job_id}` | Extraction job status + chapter preview (index + title; bodies stay backend-side) |
| POST | `/api/books/from-extraction` | Persist a finished extraction job by `{job_id}` — no chapter text round-trip |
| POST | `/api/books` | Persist book + episode rows |
| GET | `/api/books` | List all audiobooks |
| GET | `/api/books/{id}` | Book detail with chapters + audio URLs |
| POST | `/api/books/{id}/generate-audio` | Parallel TTS pipeline (background job, one worker per chapter) → MP3s in `audiobooks` bucket; chapter text read from the backend store |
| GET | `/api/books/audio/jobs/{job_id}` | TTS job progress (done/failed chapters) |
| DELETE | `/api/books/{id}` | Stop pipelines, remove MP3s from bucket, delete episodes + book |
| GET | `/api/books/enrich/lookup?title=&author=` | Open Library cover/description lookup |

### Tuning

All pipeline valves live in `backend/config.toml` (token limits, batch sizes,
concurrency, splitter backend). Environment variables override the file;
secrets stay in `.env`. To use the langChain text splitter, install
`langchain-text-splitters` yourself and set `text_splitter = "langchain"`.

## 3. Frontend

Only `NEXT_PUBLIC_FASTAPI_BASE_URL` is exposed to the browser:

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local   # set NEXT_PUBLIC_FASTAPI_BASE_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000 in a browser.

## 4. End-to-end test

1. Click **Upload Book**, drop a sample PDF → verify chapters + cover art in step 2.
2. Click **Generate audio** → confirm MP3s appear in the Supabase `audiobooks` bucket.
3. Open the book detail page → chapters list with durations; press **Listen Now**
   and navigate between pages to confirm the floating player persists.
