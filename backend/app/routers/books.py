import asyncio

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from ..config import settings
from ..deps import get_supabase_client
from ..schemas import (
    AudioJobOut,
    BookCreate,
    BookDetailOut,
    BookOut,
    ChapterIn,
    DeleteBookOut,
    EnrichmentOut,
    ExtractionJobOut,
    FromExtractionIn,
    PersistedBookOut,
    SegmentedBook,
)
from ..services import enrichment_service, pdf_service, pipeline_service
from ..services.storage_paths import public_url_to_path

router = APIRouter(prefix="/api/books", tags=["books"])


@router.post("/extract", response_model=ExtractionJobOut, status_code=202)
async def extract_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Enqueue full-book extraction: ALL pages are parsed and segmented in
    token-budgeted windows in a background task. Poll
    GET /extract/jobs/{job_id} for status; chapter bodies stay backend-side
    (persist via POST /from-extraction with the job id)."""
    if file.content_type not in ("application/pdf", "application/octet-stream", None):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    # Reject corrupt PDFs synchronously so the client gets a 400, not a
    # failed background job.
    try:
        await _probe_pdf(data)
    except Exception as exc:  # invalid/corrupt PDF
        raise HTTPException(status_code=400, detail=f"Could not parse PDF: {exc}") from exc

    filename = file.filename or "upload.pdf"
    job = await pipeline_service.create_job("extraction", filename=filename)

    background_tasks.add_task(pipeline_service.run_extraction_job, job.job_id, filename, data)
    return _extraction_job_out(job)


def _extraction_job_out(job) -> ExtractionJobOut:
    # Chapter previews only (index + title): bodies never leave the backend.
    previews = [
        {"chapter_index": c.get("chapter_index"), "title": c.get("title", "")}
        for c in (job.chapters or [])
        if isinstance(c, dict) and isinstance(c.get("chapter_index"), int)
    ]
    return ExtractionJobOut(
        job_id=job.job_id,
        kind=job.kind,
        status=job.status,
        filename=job.filename,
        num_pages=job.num_pages,
        total_chapters=job.total_chapters,
        title=job.title,
        author=job.author,
        cover_url=job.cover_url,
        description=job.description,
        chapters=previews,
        error=job.error,
    )


async def _probe_pdf(data: bytes) -> int:
    """Validate the PDF synchronously; returns the page count."""
    pages = await asyncio.to_thread(pdf_service.extract_pages, data)
    if not pages:
        raise ValueError("PDF has no readable pages.")
    return len(pages)


@router.get("/extract/jobs/{job_id}", response_model=ExtractionJobOut)
async def get_extraction_job(job_id: str):
    job = await pipeline_service.get_job(job_id)
    if job is None or job.kind != "extraction":
        raise HTTPException(status_code=404, detail="Extraction job not found.")
    return _extraction_job_out(job)


async def _persist_book(supabase, title: str, author: str, description: str, cover_url: str, chapters):
    book_res = (
        await supabase.table("books")
        .insert(
            {
                "title": title,
                "author": author,
                "description": description,
                "cover_url": cover_url,
                "total_chapters": len(chapters),
            }
        )
        .execute()
    )
    if not book_res.data:
        raise HTTPException(status_code=502, detail="Failed to persist book.")
    book = book_res.data[0]
    episodes: list[dict] = []
    if chapters:
        rows = [
            {
                "book_id": book["id"],
                "episode_number": ch.chapter_index,
                "title": ch.title,
                "duration": 0,
                "audio_url": "",
            }
            for ch in chapters
        ]
        ep_res = await supabase.table("episodes").insert(rows).execute()
        episodes = ep_res.data or []
    return {"book": book, "episodes": episodes}


@router.post("", response_model=PersistedBookOut, status_code=201)
async def create_book(body: BookCreate):
    supabase = await get_supabase_client()
    return await _persist_book(
        supabase, body.title, body.author, body.description, body.cover_url, body.chapters
    )


@router.post("/from-extraction", response_model=PersistedBookOut, status_code=201)
async def create_book_from_extraction(body: FromExtractionIn):
    """Persist a finished extraction job without the client resending text.

    Reads the chapters stored backend-side by the extraction job, so the
    extracted text is passed backend-only with no frontend round trip.
    """
    job = await pipeline_service.get_job(body.job_id)
    if job is None or job.kind != "extraction":
        raise HTTPException(status_code=404, detail="Extraction job not found.")
    if job.status != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Extraction job is {job.status}; wait for it to finish first."
            if job.status in ("queued", "running")
            else f"Extraction job failed: {job.error or 'unknown error'}",
        )
    try:
        chapters = [ChapterIn(**c) for c in job.chapters]
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Stored chapters are invalid: {exc}") from exc
    if not chapters:
        raise HTTPException(status_code=409, detail="Extraction produced no chapters.")

    supabase = await get_supabase_client()
    saved = await _persist_book(
        supabase, job.title, job.author, job.description, job.cover_url, chapters
    )
    # Hold the bodies backend-side so audio generation needs no chapter text
    # from the client.
    await pipeline_service.remember_book_chapters(saved["book"]["id"], chapters)
    return saved


@router.get("", response_model=list[BookOut])
async def list_books():
    supabase = await get_supabase_client()
    res = await supabase.table("books").select("*").order("created_at", desc=True).execute()
    return res.data or []


@router.get("/{book_id}", response_model=BookDetailOut)
async def get_book(book_id: str):
    supabase = await get_supabase_client()
    book_res = await supabase.table("books").select("*").eq("id", book_id).single().execute()
    if not book_res.data:
        raise HTTPException(status_code=404, detail="Book not found.")
    ep_res = (
        await supabase.table("episodes")
        .select("*")
        .eq("book_id", book_id)
        .order("episode_number")
        .execute()
    )
    return {**book_res.data, "episodes": ep_res.data or []}


@router.post("/{book_id}/generate-audio", response_model=AudioJobOut, status_code=202)
async def generate_audio(book_id: str, background_tasks: BackgroundTasks, body: SegmentedBook | None = None):
    """Enqueue the parallel TTS pipeline: one worker per chapter, each
    chapter's chunks synthesized concurrently. Poll GET /audio/jobs/{job_id}.

    Chapter text comes from the backend store (persisted via
    POST /from-extraction); pass an explicit body only to synthesize
    client-supplied chapters instead.
    """
    supabase = await get_supabase_client()
    book_res = await supabase.table("books").select("id").eq("id", book_id).single().execute()
    if not book_res.data:
        raise HTTPException(status_code=404, detail="Book not found.")
    if body is not None and body.chapters:
        chapters = body.chapters
        await pipeline_service.remember_book_chapters(book_id, chapters)
    else:
        chapters = await pipeline_service.get_book_chapters(book_id)
        if not chapters:
            raise HTTPException(
                status_code=400,
                detail="No chapter text stored for this book; persist it via "
                "POST /api/books/from-extraction first, or pass chapters in the body.",
            )

    job = await pipeline_service.create_job("audio", book_id=book_id)

    async def _persist(result: dict) -> None:
        client = await get_supabase_client()
        await client.table("episodes").upsert(
            {
                "book_id": book_id,
                "episode_number": result["episode_number"],
                "title": result["title"],
                "duration": result["duration"],
                "audio_url": result["audio_url"],
            },
            on_conflict="book_id,episode_number",
        ).execute()

    background_tasks.add_task(pipeline_service.run_audio_job, job.job_id, book_id, chapters, _persist)
    stored = await pipeline_service.get_job(job.job_id)
    assert stored is not None
    return AudioJobOut(
        job_id=stored.job_id,
        kind=stored.kind,
        status=stored.status,
        book_id=book_id,
        total_chapters=len(chapters),
    )


@router.get("/audio/jobs/{job_id}", response_model=AudioJobOut)
async def get_audio_job(job_id: str):
    job = await pipeline_service.get_job(job_id)
    if job is None or job.kind != "audio":
        raise HTTPException(status_code=404, detail="Audio job not found.")
    return AudioJobOut(
        job_id=job.job_id,
        kind=job.kind,
        status=job.status,
        book_id=job.book_id,
        total_chapters=job.total_chapters,
        done_chapters=job.done_chapters,
        failed_chapters=job.failed_chapters,
        error=job.error,
    )


@router.delete("/{book_id}", response_model=DeleteBookOut)
async def delete_book(book_id: str):
    """Delete an audiobook: stop its pipelines, remove MP3s from the
    bucket, then remove episode rows and the book row."""
    supabase = await get_supabase_client()
    book_res = await supabase.table("books").select("id").eq("id", book_id).single().execute()
    if not book_res.data:
        raise HTTPException(status_code=404, detail="Book not found.")

    # Stop background TTS first and wait for workers to drain, so no new
    # files are uploaded or episode rows resurrected after the delete.
    await pipeline_service.cancel_book_jobs(book_id)
    await pipeline_service.wait_for_audio_jobs(book_id)

    ep_res = (
        await supabase.table("episodes").select("audio_url").eq("book_id", book_id).execute()
    )
    paths: set[str] = set()
    for row in ep_res.data or []:
        path = public_url_to_path(row.get("audio_url") or "", settings.audiobooks_bucket)
        if path:
            paths.add(path)
    # Belt and braces: also list everything stored under the book prefix so
    # orphaned files (e.g. from a chapter that never got its URL saved) go too.
    try:
        listed = await supabase.storage.from_(settings.audiobooks_bucket).list(book_id)
    except Exception:
        listed = []
    for entry in listed or []:
        name = (entry or {}).get("name")
        if name:
            paths.add(f"{book_id}/{name}")

    removed_files = 0
    if paths:
        try:
            await supabase.storage.from_(settings.audiobooks_bucket).remove(sorted(paths))
            removed_files = len(paths)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Could not remove audio files: {exc}"
            ) from exc

    await supabase.table("episodes").delete().eq("book_id", book_id).execute()
    await supabase.table("books").delete().eq("id", book_id).execute()
    await pipeline_service.forget_book_chapters(book_id)
    return {"book_id": book_id, "removed_files": removed_files}


@router.get("/enrich/lookup", response_model=EnrichmentOut)
async def enrich_lookup(title: str, author: str = ""):
    cover_url, description = await enrichment_service.enrich_metadata(title, author)
    return EnrichmentOut(cover_url=cover_url, description=description)
