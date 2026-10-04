"""Batching + parallel-pipeline helpers for full-book processing.

stdlib only: no third-party imports so this module (and its tests) run
anywhere. TTS/PDF services delegate their pure logic here.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# Trailing closers stripped before checking for terminal punctuation.
_TRAILING_CLOSERS = "\"'”’)]}»›"
_TERMINAL_PUNCTUATION = frozenset(".!?…。！？")


def split_into_batches(page_texts: list[str], batch_pages: int) -> list[list[str]]:
    """Split all pages into consecutive windows of at most batch_pages.

    Every page is yielded exactly once — there is no page cap, so a book
    with more pages than one window produces multiple batches.
    """
    if batch_pages < 1:
        raise ValueError("batch_pages must be >= 1")
    return [page_texts[i : i + batch_pages] for i in range(0, len(page_texts), batch_pages)]


@dataclass
class ChapterDraft:
    chapter_index: int
    title: str
    body: str


@dataclass
class ChapterBuffer:
    """Holds a chapter cut off by the token limit across windows.

    When a window's trailing chapter is truncated, its partial data waits
    here; the next window completes it, and only the finished chapter flows
    to downstream steps (merge, persist, TTS).
    """

    pending: ChapterDraft | None = None

    def hold(self, chapter: ChapterDraft) -> None:
        if self.pending is None:
            self.pending = chapter
        else:
            # Defensive: never drop buffered text; concatenate instead.
            self.pending = ChapterDraft(
                chapter_index=self.pending.chapter_index,
                title=self.pending.title or chapter.title,
                body=merge_continued_body(self.pending.body, chapter.body),
            )

    def take(self) -> ChapterDraft | None:
        pending, self.pending = self.pending, None
        return pending


def merge_chapters(batches: list[list[ChapterDraft]]) -> list[ChapterDraft]:
    """Merge per-batch chapters into one renumbered sequence (1..N)."""
    merged: list[ChapterDraft] = []
    for batch in batches:
        for ch in batch:
            merged.append(
                ChapterDraft(
                    chapter_index=len(merged) + 1,
                    title=ch.title,
                    body=ch.body,
                )
            )
    return merged


def _split_with_langchain(text: str, chunk_size: int, overlap_chars: int) -> list[str]:
    """Split via langChain's RecursiveCharacterTextSplitter (optional dep).

    Raises ImportError when langchain-text-splitters is not installed, so
    callers fall back to the stdlib splitter.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max(1, chunk_size),
        chunk_overlap=max(0, min(overlap_chars, max(1, chunk_size) - 1)),
    )
    return [c for c in (s.strip() for s in splitter.split_text(text)) if c]


def split_text_chunks(
    text: str,
    max_chars: int,
    splitter: str = "stdlib",
    overlap_chars: int = 0,
) -> list[str]:
    """Chunk text along sentence boundaries, each chunk <= max_chars.

    A single sentence longer than max_chars becomes its own chunk.
    ``splitter="langchain"`` uses RecursiveCharacterTextSplitter instead
    (requires langchain-text-splitters to be installed).
    """
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")
    if splitter == "langchain":
        return _split_with_langchain(text, max_chars, overlap_chars)
    if splitter != "stdlib":
        raise ValueError(f"unknown splitter: {splitter!r}")
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current = f"{current} {sentence}"
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return chunks


def estimate_tokens(text: str, chars_per_token: float = 4.0) -> int:
    """Rough token estimate without a tokenizer dependency."""
    if chars_per_token <= 0:
        raise ValueError("chars_per_token must be > 0")
    return int(len(text) / chars_per_token) + (1 if text else 0)


def ends_complete(text: str) -> bool:
    """Whether chapter text ends on a terminal boundary.

    Used to spot a chapter cut off by the model's token limit: a body that
    does not end with sentence-terminal punctuation is held in the buffer
    instead of flowing downstream.
    """
    stripped = text.strip().rstrip(_TRAILING_CLOSERS).rstrip()
    if not stripped:
        return True
    return stripped[-1] in _TERMINAL_PUNCTUATION


def split_text_windows(
    text: str,
    token_limit: int,
    chars_per_token: float = 4.0,
    splitter: str = "stdlib",
    overlap_chars: int = 0,
) -> list[str]:
    """Split text into sentence-aware windows within a token budget.

    Each window holds at most ``token_limit`` estimated tokens; a single
    sentence larger than the budget becomes its own window.
    ``splitter="langchain"`` uses RecursiveCharacterTextSplitter instead
    (requires langchain-text-splitters to be installed).
    """
    if token_limit < 1:
        raise ValueError("token_limit must be >= 1")
    if splitter == "langchain":
        return _split_with_langchain(
            text, int(token_limit * chars_per_token), overlap_chars
        )
    if splitter != "stdlib":
        raise ValueError(f"unknown splitter: {splitter!r}")
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    windows: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        needed = estimate_tokens(sentence, chars_per_token) + (1 if current else 0)
        if current and current_tokens + needed > token_limit:
            windows.append(" ".join(current))
            current = []
            current_tokens = 0
        current.append(sentence)
        current_tokens += estimate_tokens(sentence, chars_per_token) + (0 if len(current) == 1 else 1)
    if current:
        windows.append(" ".join(current))
    return windows


def split_pages_into_token_windows(
    page_texts: list[str],
    token_limit: int,
    chars_per_token: float = 4.0,
    max_pages: int = 0,
    splitter: str = "stdlib",
    overlap_chars: int = 0,
) -> list[list[str]]:
    """Pack whole pages into consecutive windows within a token budget.

    Pages are never split unless a single page alone exceeds the budget (it
    is then sentence-split, via the stdlib or langChain splitter).
    ``max_pages`` caps pages per window (0 = no cap). Every page is yielded
    exactly once, in order.
    """
    if token_limit < 1:
        raise ValueError("token_limit must be >= 1")
    if max_pages < 0:
        raise ValueError("max_pages must be >= 0")
    windows: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for page in page_texts:
        needed = estimate_tokens(page, chars_per_token)
        if estimate_tokens(page, chars_per_token) > token_limit:
            if current:
                windows.append(current)
                current = []
                current_tokens = 0
            for chunk in split_text_windows(
                page, token_limit, chars_per_token, splitter, overlap_chars
            ):
                windows.append([chunk])
            continue
        if current and (
            current_tokens + needed > token_limit
            or (max_pages > 0 and len(current) >= max_pages)
        ):
            windows.append(current)
            current = []
            current_tokens = 0
        current.append(page)
        current_tokens += needed
    if current:
        windows.append(current)
    return windows


def decode_partial_json_string(raw: str, quote: int) -> str | None:
    """Best-effort decode of the JSON string opening at index ``quote``.

    Unlike strict decoding, this also returns the content so far when the
    string is unterminated (model output cut off inside it). Returns None
    when the content cannot be decoded.
    """
    chunks: list[str] = []
    i = quote + 1
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == "\\":
            if i + 1 >= n:
                break  # dangling escape at the cut point: drop it
            chunks.append(c)
            chunks.append(raw[i + 1])
            i += 2
        elif c == '"':
            break
        elif ord(c) < 0x20:
            chunks.append(" ")
            i += 1
        else:
            chunks.append(c)
            i += 1
    try:
        return json.loads('"' + "".join(chunks) + '"')
    except json.JSONDecodeError:
        return None


def find_string_field_from(raw: str, field: str, start: int) -> str:
    """Best-effort read of a string field at/after ``start``, tolerating a
    cut-off (unterminated) value. Returns "" when absent or undecodable."""
    m = re.search(r'"' + re.escape(field) + r'"\s*:', raw[start:])
    if not m:
        return ""
    i = start + m.end()
    while i < len(raw) and raw[i] in " \t\r\n":
        i += 1
    if i >= len(raw) or raw[i] != '"':
        return ""
    decoded = decode_partial_json_string(raw, i)
    return decoded if decoded is not None else ""


def extract_partial_chapter(raw: str) -> ChapterDraft | None:
    """Pull a partial chapter from truncated model JSON with zero complete
    chapter objects (cut off inside the first chapter's body).

    Returns the chapter index/title/body-so-far so the caller can buffer it
    for the next window instead of failing the whole book. Returns None when
    nothing chapter-like survived.
    """
    m = re.search(r'"chapter_index"\s*:\s*(\d+)', raw)
    if not m:
        return None
    try:
        index = int(m.group(1))
    except ValueError:
        return None
    title = find_string_field_from(raw, "title", m.end())
    body = find_string_field_from(raw, "body", m.end())
    if not title and not body:
        return None
    return ChapterDraft(chapter_index=index, title=title, body=body)


def window_page_label(window_pages: list[str]) -> str:
    """Human-readable page range for a window (for error messages)."""
    nums = [int(n) for page in window_pages for n in re.findall(r"PAGE\s+(\d+)", page)]
    if not nums:
        return f"{len(window_pages)} page(s)"
    if nums[0] == nums[-1]:
        return f"page {nums[0]}"
    return f"pages {nums[0]}-{nums[-1]}"


def merge_continued_body(pending_body: str, next_body: str) -> str:
    """Join a buffered (truncated) chapter body with its continuation.

    When the model echoes the buffered text back as part of the completed
    body, the duplicate is removed; otherwise the parts are concatenated.
    """
    if not pending_body:
        return next_body
    if not next_body:
        return pending_body
    if next_body.startswith(pending_body):
        return next_body
    # Splice on overlap: the start of the continuation may repeat the tail
    # of the buffered text.
    probe = next_body[:120]
    idx = pending_body.rfind(probe) if probe.strip() else -1
    if idx != -1:
        return pending_body[:idx] + next_body
    return pending_body.rstrip() + " " + next_body.lstrip()


@dataclass
class ChapterJobState:
    chapter_index: int
    title: str
    status: str = "queued"  # queued | synthesizing | done | failed
    audio_url: str = ""
    error: str = ""


@dataclass
class PipelineProgress:
    total: int = 0
    done: int = 0
    failed: int = 0
    chapters: list[ChapterJobState] = field(default_factory=list)

    @classmethod
    def for_chapters(cls, chapters: list[ChapterDraft]) -> "PipelineProgress":
        return cls(
            total=len(chapters),
            chapters=[
                ChapterJobState(chapter_index=c.chapter_index, title=c.title) for c in chapters
            ],
        )

    def by_index(self) -> dict[int, ChapterJobState]:
        return {c.chapter_index: c for c in self.chapters}

    def mark_done(self, chapter_index: int, audio_url: str) -> None:
        for ch in self.chapters:
            if ch.chapter_index == chapter_index:
                ch.status = "done"
                ch.audio_url = audio_url
                break
        self.done += 1

    def mark_failed(self, chapter_index: int, error: str) -> None:
        for ch in self.chapters:
            if ch.chapter_index == chapter_index:
                ch.status = "failed"
                ch.error = error
                break
        self.failed += 1
