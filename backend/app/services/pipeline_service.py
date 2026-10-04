"""Background batch pipelines: full-book extraction and parallel TTS.

Both pipelines run as asyncio background tasks so uploads return
immediately. Progress is kept in an in-memory job store that routers
expose for polling. Persistence callbacks are injected by the router so
this module never touches Supabase directly.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from ..schemas import ChapterIn
from . import enrichment_service, pdf_service, segmentation_service, tts_service
from .batching import ChapterDraft, PipelineProgress


# Extracted chapter bodies, keyed by book id. Persist holds the bodies here
# so audio generation reads them backend-side — the frontend never shuttles
# extracted text back and forth.
_book_chapters: dict[str, list[ChapterIn]] = {}


async def remember_book_chapters(book_id: str, chapters: list[ChapterIn]) -> None:
    async with _lock:
        _book_chapters[book_id] = list(chapters)


async def get_book_chapters(book_id: str) -> list[ChapterIn] | None:
    async with _lock:
        chapters = _book_chapters.get(book_id)
        return list(chapters) if chapters is not None else None


async def forget_book_chapters(book_id: str) -> None:
    async with _lock:
        _book_chapters.pop(book_id, None)


@dataclass
class JobState:
    job_id: str = ""
    kind: str = ""  # "extraction" | "audio"
    status: str = "queued"  # queued | running | done | failed
    filename: str = ""
    book_id: str = ""
    num_pages: int = 0
    extracted_pages: int = 0
    total_chapters: int = 0
    done_chapters: int = 0
    failed_chapters: int = 0
    title: str = ""
    author: str = ""
    cover_url: str = ""
    description: str = ""
    chapters: list[dict] = field(default_factory=list)
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


_jobs: dict[str, JobState] = {}
_lock = asyncio.Lock()

# Book ids whose background work must stop (deleted while a job runs).
_cancelled_books: set[str] = set()


async def cancel_book_jobs(book_id: str) -> None:
    """Flag a book's pipelines to stop; workers skip remaining chapters."""
    async with _lock:
        _cancelled_books.add(book_id)


def is_book_cancelled(book_id: str) -> bool:
    return book_id in _cancelled_books


async def audio_jobs_for_book(book_id: str) -> list[JobState]:
    async with _lock:
        return [j for j in _jobs.values() if j.kind == "audio" and j.book_id == book_id]


async def wait_for_audio_jobs(book_id: str, timeout_seconds: float = 30.0) -> None:
    """Wait until no audio job for the book is still queued/running."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        jobs = await audio_jobs_for_book(book_id)
        if all(j.status not in ("queued", "running") for j in jobs):
            return
        await asyncio.sleep(0.25)


async def create_job(kind: str, filename: str = "", book_id: str = "") -> JobState:
    job = JobState(job_id=uuid.uuid4().hex, kind=kind, filename=filename, book_id=book_id)
    async with _lock:
        _jobs[job.job_id] = job
    return job


async def get_job(job_id: str) -> JobState | None:
    async with _lock:
        return _jobs.get(job_id)


async def update_job(job_id: str, **fields: object) -> None:
    async with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = time.time()


async def run_extraction_job(
    job_id: str,
    filename: str,
    pdf_bytes: bytes,
) -> None:
    """Background task: extract ALL pages, segment in token-budgeted
    windows with chapter-continuation buffering, then enrich.

    The segmented chapters stay in the backend job store; downstream steps
    (persist, audio) read them from here — no frontend round trip.
    """
    from ..config import settings

    await update_job(job_id, status="running")
    try:
        # Run CPU-ish PDF parsing off the event loop thread.
        page_texts = await asyncio.to_thread(pdf_service.extract_pages, pdf_bytes)
        await update_job(job_id, num_pages=len(page_texts), extracted_pages=len(page_texts))

        segmented = await segmentation_service.segment_page_batches(
            page_texts,
            batch_pages=settings.extraction_batch_pages,
        )
        cover_url, description = await enrichment_service.enrich_metadata(
            segmented.title, segmented.author
        )
        await update_job(
            job_id,
            status="done",
            title=segmented.title,
            author=segmented.author,
            cover_url=cover_url,
            description=description,
            total_chapters=len(segmented.chapters),
            done_chapters=len(segmented.chapters),
            chapters=[c.model_dump() for c in segmented.chapters],
        )
    except Exception as exc:
        await update_job(job_id, status="failed", error=str(exc))


async def run_audio_job(
    job_id: str,
    book_id: str,
    chapters: list[ChapterIn],
    on_chapter_done: Callable[[dict], Awaitable[None]] | None = None,
) -> None:
    """Background task: parallel per-chapter TTS pipeline.

    Each chapter is handled by its own worker (one chapter per process),
    pulling from a shared queue so chapters start as soon as workers free
    up instead of waiting for a sequential loop.
    """
    from ..config import settings

    drafts = [ChapterDraft(c.chapter_index, c.title, c.body) for c in chapters]
    progress = PipelineProgress.for_chapters(drafts)
    await update_job(
        job_id,
        status="running",
        book_id=book_id,
        total_chapters=len(chapters),
        chapters=[c.model_dump() for c in chapters],
    )

    async def _persist_and_track(result: dict) -> None:
        # progress.done is updated synchronously by the worker before this
        # callback runs, so it can't lose counts the way read-modify-write
        # on the job store could under parallel workers.
        await update_job(job_id, done_chapters=progress.done)
        # Skip persisting when the book was deleted mid-pipeline so episode
        # rows are not resurrected after the delete.
        if is_book_cancelled(book_id):
            return
        if on_chapter_done is not None:
            await on_chapter_done(result)

    try:
        await tts_service.generate_chapters_parallel(
            book_id,
            chapters,
            progress,
            max_concurrency=settings.tts_max_concurrency,
            on_chapter_done=_persist_and_track,
            should_stop=lambda: is_book_cancelled(book_id),
        )
    except Exception as exc:
        await update_job(job_id, status="failed", error=str(exc))
        return
    if is_book_cancelled(book_id):
        await update_job(job_id, status="cancelled", error="Book was deleted; pipeline stopped.")
    else:
        await update_job(
            job_id,
            status="done" if progress.failed == 0 else "failed",
            failed_chapters=progress.failed,
            error="" if progress.failed == 0 else f"{progress.failed} chapter(s) failed TTS",
        )
    async with _lock:
        _cancelled_books.discard(book_id)
