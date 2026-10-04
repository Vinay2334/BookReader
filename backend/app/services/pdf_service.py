import io
from dataclasses import dataclass, field

from pypdf import PdfReader

from ..config import settings


@dataclass
class ExtractedPdf:
    num_pages: int
    full_text: str
    front_matter_text: str
    front_matter_pages: int
    pdf_title: str
    pdf_author: str
    # One entry per page, in order — the full book, never capped.
    page_texts: list[str] = field(default_factory=list)


def extract_pages(data: bytes) -> list[str]:
    """Extract per-page texts for the whole document, in page order."""
    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"\n\n===== PAGE {i} =====\n{text.strip()}")
    return pages


def extract_pdf(data: bytes) -> ExtractedPdf:
    """Extract raw text + metadata, preserving page demarcations."""
    reader = PdfReader(io.BytesIO(data))
    page_texts: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        page_texts.append(f"\n\n===== PAGE {i} =====\n{text.strip()}")
    num_pages = len(page_texts)

    meta = reader.metadata
    pdf_title = str(meta.title or "") if meta else ""
    pdf_author = str(meta.author or "") if meta else ""

    front_matter_pages = min(num_pages, settings.front_matter_max_pages)
    front_matter_text = "\n".join(page_texts[:front_matter_pages])
    return ExtractedPdf(
        num_pages=num_pages,
        full_text="\n".join(page_texts),
        front_matter_text=front_matter_text,
        front_matter_pages=front_matter_pages,
        pdf_title=pdf_title,
        pdf_author=pdf_author,
        page_texts=page_texts,
    )
