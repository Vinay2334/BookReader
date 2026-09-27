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


class PdfMetadata(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    num_pages: int = 0
