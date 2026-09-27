import io
from dataclasses import dataclass

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


def extract_pdf(data: bytes) -> ExtractedPdf:
    """Extract raw text + metadata, preserving page demarcations."""
    reader = PdfReader(io.BytesIO(data))
    num_pages = len(reader.pages)
    page_texts: list[str] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        page_texts.append(f"\n\n===== PAGE {i} =====\n{text.strip()}")

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
    )
