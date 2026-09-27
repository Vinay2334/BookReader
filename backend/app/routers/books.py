from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..deps import get_supabase_client
from ..schemas import (
    AudioGenerationOut,
    BookCreate,
    BookDetailOut,
    BookOut,
    EnrichmentOut,
    EpisodeOut,
    ExtractPreview,
    PersistedBookOut,
    SegmentedBook,
)
from ..services import enrichment_service, pdf_service, segmentation_service, tts_service

router = APIRouter(prefix="/api/books", tags=["books"])


class ExtractedPayload(BaseModel):
    filename: str
    segmented: SegmentedBook
    cover_url: str = ""
    description: str = ""
    num_pages: int = 0
    front_matter_pages: int = 0
    front_matter_text: str = ""


_last_extraction: dict[str, ExtractedPayload] = {}


@router.post("/extract", response_model=ExtractPreview)
async def extract_pdf(file: UploadFile = File(...)):
    if file.content_type not in ("application/pdf", "application/octet-stream", None):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        extracted = pdf_service.extract_pdf(data)
        print(f"Extracted {extracted.num_pages} pages, front matter: {extracted.front_matter_pages} pages")
    except Exception as exc:  # invalid/corrupt PDF
        raise HTTPException(status_code=400, detail=f"Could not parse PDF: {exc}") from exc
    try:
        segmented = await segmentation_service.segment_front_matter(extracted.front_matter_text)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Chapter segmentation failed: {exc}") from exc
    cover_url, description = await enrichment_service.enrich_metadata(segmented.title, segmented.author)
    _last_extraction["latest"] = ExtractedPayload(
        filename=file.filename or "upload.pdf",
        segmented=segmented,
        cover_url=cover_url,
        description=description,
        num_pages=extracted.num_pages,
        front_matter_pages=extracted.front_matter_pages,
        front_matter_text=extracted.front_matter_text,
    )
    payload = _last_extraction["latest"]
    return ExtractPreview(
        filename=payload.filename,
        num_pages=payload.num_pages,
        front_matter_pages=payload.front_matter_pages,
        front_matter_text=payload.front_matter_text,
    )


@router.get("/extract/preview")
async def extract_preview():
    payload = _last_extraction.get("latest")
    if payload is None:
        raise HTTPException(status_code=404, detail="No extraction has been run yet.")
    return {
        "filename": payload.filename,
        "title": payload.segmented.title,
        "author": payload.segmented.author,
        "cover_url": payload.cover_url,
        "description": payload.description,
        "chapters": [c.model_dump() for c in payload.segmented.chapters],
    }


@router.post("", response_model=PersistedBookOut, status_code=201)
async def create_book(body: BookCreate):
    supabase = await get_supabase_client()
    book_res = (
        await supabase.table("books")
        .insert(
            {
                "title": body.title,
                "author": body.author,
                "description": body.description,
                "cover_url": body.cover_url,
                "total_chapters": len(body.chapters),
            }
        )
        .execute()
    )
    if not book_res.data:
        raise HTTPException(status_code=502, detail="Failed to persist book.")
    book = book_res.data[0]
    episodes: list[dict] = []
    if body.chapters:
        rows = [
            {
                "book_id": book["id"],
                "episode_number": ch.chapter_index,
                "title": ch.title,
                "duration": 0,
                "audio_url": "",
            }
            for ch in body.chapters
        ]
        ep_res = await supabase.table("episodes").insert(rows).execute()
        episodes = ep_res.data or []
    return {"book": book, "episodes": episodes}


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


@router.post("/{book_id}/generate-audio", response_model=AudioGenerationOut)
async def generate_audio(book_id: str, background_tasks: BackgroundTasks, body: SegmentedBook):
    supabase = await get_supabase_client()
    book_res = await supabase.table("books").select("id").eq("id", book_id).single().execute()
    if not book_res.data:
        raise HTTPException(status_code=404, detail="Book not found.")

    async def _run():
        client = await get_supabase_client()
        for ch in body.chapters:
            result = await tts_service.generate_chapter_audio(
                book_id, ch.chapter_index, ch.title, ch.body
            )
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

    background_tasks.add_task(_run)
    existing = (
        await supabase.table("episodes").select("*").eq("book_id", book_id).order("episode_number").execute()
    )
    return {
        "book_id": book_id,
        "episodes": [EpisodeOut(**row) for row in (existing.data or [])],
    }


@router.get("/enrich/lookup", response_model=EnrichmentOut)
async def enrich_lookup(title: str, author: str = ""):
    cover_url, description = await enrichment_service.enrich_metadata(title, author)
    return EnrichmentOut(cover_url=cover_url, description=description)
