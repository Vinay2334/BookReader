from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChapterIn(BaseModel):
    chapter_index: int = Field(ge=1)
    title: str
    body: str


class SegmentedBook(BaseModel):
    title: str
    author: str = ""
    chapters: list[ChapterIn]


class ExtractPreview(BaseModel):
    filename: str
    num_pages: int
    front_matter_pages: int
    front_matter_text: str


class BookCreate(BaseModel):
    title: str
    author: str = ""
    description: str = ""
    cover_url: str = ""
    chapters: list[ChapterIn]


class EpisodeOut(BaseModel):
    id: UUID
    book_id: UUID
    episode_number: int
    title: str
    duration: int
    audio_url: str


class BookOut(BaseModel):
    id: UUID
    title: str
    author: str
    description: str
    cover_url: str
    total_chapters: int


class BookDetailOut(BookOut):
    episodes: list[EpisodeOut] = []


class EnrichmentOut(BaseModel):
    cover_url: str = ""
    description: str = ""


class PersistedBookOut(BaseModel):
    book: BookOut
    episodes: list[EpisodeOut]


class AudioGenerationOut(BaseModel):
    book_id: UUID
    episodes: list[EpisodeOut]


class ChapterPreview(BaseModel):
    """Chapter listing for the extraction status poll: index + title only.

    Full chapter bodies stay backend-side (job store → persist → audio);
    the frontend never round-trips extracted text.
    """

    chapter_index: int = Field(ge=1)
    title: str


class FromExtractionIn(BaseModel):
    job_id: str


class ExtractionJobOut(BaseModel):
    job_id: str
    kind: str = "extraction"
    status: str
    filename: str = ""
    num_pages: int = 0
    total_chapters: int = 0
    title: str = ""
    author: str = ""
    cover_url: str = ""
    description: str = ""
    chapters: list[ChapterPreview] = []
    error: str = ""


class AudioJobOut(BaseModel):
    job_id: str
    kind: str = "audio"
    status: str
    book_id: str = ""
    total_chapters: int = 0
    done_chapters: int = 0
    failed_chapters: int = 0
    error: str = ""


class DeleteBookOut(BaseModel):
    book_id: str
    removed_files: int = 0


class PdfMetadata(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    num_pages: int = 0
