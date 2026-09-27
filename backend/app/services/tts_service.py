import re
import uuid

from ..config import settings
from ..deps import get_openai_client, get_supabase_client

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, max_chars: int = 0) -> list[str]:
    """Chunk text along natural sentence boundaries under max_chars."""
    limit = max_chars or settings.max_tts_chunk_chars
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= limit:
            current = f"{current} {sentence}"
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


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


async def generate_chapter_audio(book_id: str, episode_number: int, title: str, body: str) -> dict:
    chunks = chunk_text(body)
    segments: list[bytes] = []
    for chunk in chunks:
        segments.append(await synthesize_chunk(chunk))
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
