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
| POST | `/api/books/extract` | Multipart PDF upload → segmentation + enrichment preview |
| GET | `/api/books/extract/preview` | Latest extraction preview (chapters, cover art) |
| POST | `/api/books` | Persist book + episode rows |
| GET | `/api/books` | List all audiobooks |
| GET | `/api/books/{id}` | Book detail with chapters + audio URLs |
| POST | `/api/books/{id}/generate-audio` | TTS pipeline (background task) → MP3s in `audiobooks` bucket |
| GET | `/api/books/enrich/lookup?title=&author=` | Open Library cover/description lookup |

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
