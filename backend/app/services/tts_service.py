import asyncio
import uuid
from collections.abc import Awaitable, Callable

from ..config import settings
from ..deps import get_openai_client, get_supabase_client
from ..schemas import ChapterIn
from .batching import PipelineProgress, split_text_chunks


def chunk_text(text: str, max_chars: int = 0) -> list[str]:
    """Chunk text along natural sentence boundaries under max_chars.

    Uses the configured splitter backend (stdlib by default; langChain when
    selected and installed — overlap stays 0 so audio never duplicates).
    """
    return split_text_chunks(
        text,
        max_chars or settings.max_tts_chunk_chars,
        splitter=settings.segmentation_text_splitter,
    )


async def synthesize_chunk(text: str) -> bytes:
    client = get_openai_client()
    async with client.audio.speech.with_streaming_response.create(
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        input=text,
        response_format="mp3",
    ) as response:
        return await response.read()


def estimate_duration_seconds(audio: bytes, bitrate_kbps: int = 128) -> int:
    if not audio:
        return 0
    return max(1, round(len(audio) * 8 / (bitrate_kbps * 1000)))


async def _synthesize_chunks_concurrent(texts: list[str], max_concurrency: int = 0) -> list[bytes]:
    """Synthesize TTS chunks concurrently, preserving chunk order."""
    limit = max_concurrency or settings.tts_chunk_concurrency
    semaphore = asyncio.Semaphore(max(1, limit))

    async def _one(text: str) -> bytes:
        async with semaphore:
            return await synthesize_chunk(text)

    return list(await asyncio.gather(*(_one(t) for t in texts)))


async def generate_chapter_audio(book_id: str, episode_number: int, title: str, body: str) -> dict:
    chunks = chunk_text(body)
    segments = await _synthesize_chunks_concurrent(chunks)
    combined = b"".join(segments)
    duration = estimate_duration_seconds(combined)

    storage_path = f"{book_id}/{episode_number}-{uuid.uuid4().hex}.mp3"
    supabase = await get_supabase_client()
    await supabase.storage.from_(settings.audiobooks_bucket).upload(
        storage_path, combined, {"content-type": "audio/mpeg"}
    )
    public = await supabase.storage.from_(settings.audiobooks_bucket).get_public_url(storage_path)
    audio_url = public if isinstance(public, str) else public.get("publicUrl", "")
    return {"episode_number": episode_number, "title": title, "duration": duration, "audio_url": audio_url}


async def generate_chapters_parallel(
    book_id: str,
    chapters: list[ChapterIn],
    progress: PipelineProgress,
    max_concurrency: int = 0,
    on_chapter_done: Callable[[dict], Awaitable[None]] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[dict]:
    """TTS pipeline: each chapter is processed by its own parallel worker.

    Chapters flow through an asyncio queue consumed by `max_concurrency`
    workers, so chapter N+1 starts while chapter N is still synthesizing.
    `on_chapter_done` fires per chapter (e.g. persist + progress update).
    When `should_stop` returns True (e.g. the book was deleted), workers
    skip remaining chapters so the pipeline drains quickly.
    Results are returned in chapter order.
    """
    limit = max(1, max_concurrency or settings.tts_max_concurrency)
    queue: asyncio.Queue[ChapterIn | None] = asyncio.Queue()
    for ch in chapters:
        queue.put_nowait(ch)
    for _ in range(limit):
        queue.put_nowait(None)  # one sentinel per worker
    results: dict[int, dict] = {}

    async def _worker() -> None:
        while True:
            chapter = await queue.get()
            try:
                if chapter is None:
                    return
                if should_stop is not None and should_stop():
                    continue
                stats = progress.by_index().get(chapter.chapter_index)
                if stats is not None:
                    stats.status = "synthesizing"
                try:
                    result = await generate_chapter_audio(
                        book_id, chapter.chapter_index, chapter.title, chapter.body
                    )
                except Exception as exc:
                    progress.mark_failed(chapter.chapter_index, str(exc))
                    continue
                results[chapter.chapter_index] = result
                progress.mark_done(chapter.chapter_index, result["audio_url"])
                if on_chapter_done is not None:
                    await on_chapter_done(result)
            finally:
                queue.task_done()

    workers = [asyncio.create_task(_worker()) for _ in range(limit)]
    await queue.join()
    await asyncio.gather(*workers)
    return [results[i] for i in sorted(results)]
