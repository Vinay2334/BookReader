import json
import re

from ..deps import get_openai_client
from ..config import settings
from ..schemas import ChapterIn, SegmentedBook
from .batching import (
    ChapterDraft,
    ends_complete,
    estimate_tokens,
    extract_partial_chapter,
    merge_continued_body,
    split_pages_into_token_windows,
    split_text_windows,
    window_page_label,
)


class WindowSegmentationError(ValueError):
    """A window failed with no complete chapters; may carry partial data."""

    def __init__(self, message: str, partial: ChapterDraft | None = None):
        super().__init__(message)
        self.partial = partial


# Max times a failing window is split into smaller halves before giving up.
MAX_WINDOW_SPLITS = 4
# Windows this small (estimated tokens) that still fail are treated as
# atomic: their partial text is buffered instead of split further.
MIN_SPLIT_TOKENS = 200


SYSTEM_PROMPT = (
    "You segment book front matter / table of contents into clean chapters. "
    "Strip headers, footers, and page numbers. "
    'Respond with a JSON object shaped like {"title": str, "author": str, '
    '"chapters": [{"chapter_index": int, "title": str, "body": str}]}.'
)

CONTINUATION_PROMPT = (
    "The previous window was cut off mid-chapter by the token limit. "
    "Its partial text is given first under CONTINUATION OF. Continue that "
    "same chapter to completion, then segment any further chapters in the "
    "new text. Return the continued chapter FIRST with its COMPLETE body "
    "(the given partial text plus its continuation merged, in order)."
)


def _decode_string_at(raw: str, quote: int) -> tuple[str, int] | None:
    """Decode the JSON string whose opening quote sits at index `quote`.

    Returns (value, index just past the closing quote), or None when the
    string is unterminated (e.g. model output was cut off inside it).
    """
    chunks: list[str] = []
    i = quote + 1
    n = len(raw)
    while i < n:
        c = raw[i]
        if c == "\\":
            if i + 1 >= n:
                return None
            chunks.append(c)
            chunks.append(raw[i + 1])
            i += 2
        elif c == '"':
            try:
                return json.loads('"' + "".join(chunks) + '"'), i + 1
            except json.JSONDecodeError:
                return None
        elif ord(c) < 0x20:
            return None  # literal control char: not valid JSON, give up here
        else:
            chunks.append(c)
            i += 1
    return None


def _first_string_field(raw: str, field: str) -> str:
    """Best-effort read of a top-level string field from possibly-truncated JSON."""
    m = re.search(r'"' + re.escape(field) + r'"\s*:', raw)
    if not m:
        return ""
    i = m.end()
    while i < len(raw) and raw[i] in " \t\r\n":
        i += 1
    if i >= len(raw) or raw[i] != '"':
        return ""
    decoded = _decode_string_at(raw, i)
    return decoded[0] if decoded else ""


def _balanced_object_spans(raw: str) -> list[str]:
    """Yield every brace-balanced `{...}` span, respecting string literals."""
    spans: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        if raw[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        closed = False
        while j < n:
            c = raw[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    spans.append(raw[i : j + 1])
                    closed = True
                    break
            j += 1
        # On an unclosed object, step one char forward (not past the end) so
        # complete objects nested inside truncated output are still found.
        i = j + 1 if closed else i + 1
    return spans


def _without_literal_controls(raw: str) -> str:
    """Replace literal control chars inside strings (stray newlines/tabs the
    model sometimes emits) with spaces so the JSON parses as intended."""
    out: list[str] = []
    in_str = False
    esc = False
    for c in raw:
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            elif ord(c) < 0x20:
                out.append(" ")
                continue
        elif c == '"':
            in_str = True
        out.append(c)
    return "".join(out)


def _parse_or_salvage(raw: str) -> SegmentedBook | None:
    """Parse model JSON, repairing common defects. Returns None when nothing
    usable survived (caller retries or raises)."""
    try:
        return SegmentedBook.model_validate_json(raw)
    except ValueError:
        pass
    salvaged = _salvage_truncated_segmentation(raw)
    if salvaged is not None:
        return salvaged
    fixed = _without_literal_controls(raw)
    if fixed != raw:
        try:
            return SegmentedBook.model_validate_json(fixed)
        except ValueError:
            pass
        return _salvage_truncated_segmentation(fixed)
    return None


def _salvage_truncated_segmentation(raw: str) -> SegmentedBook | None:
    """Recover a usable book from cut-off model JSON.

    Keeps every complete chapter object; returns None when nothing usable
    survived (caller then retries once, then raises a helpful error).
    """
    chapters: list[dict] = []
    for span in _balanced_object_spans(raw):
        try:
            obj = json.loads(span)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(obj, dict)
            and isinstance(obj.get("chapter_index"), int)
            and isinstance(obj.get("title"), str)
            and isinstance(obj.get("body"), str)
        ):
            chapters.append(obj)
    if not chapters:
        return None
    return SegmentedBook.model_validate(
        {
            "title": _first_string_field(raw, "title"),
            "author": _first_string_field(raw, "author"),
            "chapters": chapters,
        }
    )


def _finish_truncated(completion) -> bool:
    """Whether the model stopped because it hit the token limit."""
    try:
        return completion.choices[0].finish_reason == "length"
    except (AttributeError, IndexError):
        return False


async def segment_text_detailed(
    batch_text: str,
    continuation: ChapterDraft | None = None,
) -> tuple[SegmentedBook, bool]:
    """Segment one token-budgeted window.

    Returns (book, truncated): ``truncated`` is True when the model hit the
    token limit, so the caller buffers the trailing chapter instead of
    letting a half chapter flow downstream.
    """
    client = get_openai_client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if continuation is not None:
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{CONTINUATION_PROMPT}\n\nCONTINUATION OF "
                    f"chapter '{continuation.title}':\n{continuation.body}\n\n"
                    f"NEW TEXT:\n{batch_text}"
                ),
            }
        )
    else:
        messages.append({"role": "user", "content": batch_text})
    attempts = 1 + max(0, settings.segmentation_max_retries)
    for _ in range(attempts):
        completion = await client.chat.completions.create(
            model=settings.openai_segmentation_model,
            response_format={"type": "json_object"},
            max_tokens=settings.openai_segmentation_max_tokens,
            messages=messages,
        )
        raw = completion.choices[0].message.content or "{}"
        try:
            return SegmentedBook.model_validate_json(raw), _finish_truncated(completion)
        except ValueError:
            pass
        book = _parse_or_salvage(raw)
        if book is not None:
            # Salvage only runs when strict parsing failed, i.e. the JSON
            # was cut off — treat the tail chapter as truncated.
            return book, True
        # Nothing usable at all (e.g. cut off after a few chars): the
        # failure is usually transient, so the loop retries the request.
    # No complete chapters survived, but the cut-off head of the first
    # chapter may still be usable — carry it so the caller can buffer it
    # for the next window instead of failing the whole book.
    raise WindowSegmentationError(
        "Model returned truncated or invalid JSON with no complete chapters.",
        partial=extract_partial_chapter(raw),
    )


async def segment_text(
    batch_text: str,
    continuation: ChapterDraft | None = None,
) -> SegmentedBook:
    """Segment one page-window of text (single LLM call, plus retries)."""
    book, _ = await segment_text_detailed(batch_text, continuation)
    return book


async def segment_front_matter(front_matter_text: str) -> SegmentedBook:
    return await segment_text(front_matter_text)


async def segment_page_batches(
    page_texts: list[str],
    batch_pages: int = 0,
    token_limit: int = 0,
) -> SegmentedBook:
    """Segment the whole book in token-budgeted windows, in page order.

    Pages are packed into windows that fit ``token_limit`` (config valve, so
    oversized text never exceeds the model's token limit). Windows run in
    order: when a window's trailing chapter is truncated, its partial data
    waits in a buffer and the next window completes it — only finished
    chapters flow to downstream steps. A window that yields no complete
    chapters is split into halves and retried (covering the same text, so
    nothing is skipped); an atomic failure buffers whatever partial text
    survived instead of failing the whole book. Chapters merge into one
    renumbered sequence.
    """
    per_window_pages = batch_pages or settings.extraction_batch_pages
    limit = token_limit or settings.segmentation_token_limit
    chars_per_token = settings.segmentation_chars_per_token
    splitter = settings.segmentation_text_splitter
    overlap_chars = settings.segmentation_text_splitter_overlap_chars
    windows = split_pages_into_token_windows(
        page_texts,
        limit,
        chars_per_token,
        max_pages=per_window_pages,
        splitter=splitter,
        overlap_chars=overlap_chars,
    )
    if not windows:
        return SegmentedBook(title="", author="", chapters=[])

    title = ""
    author = ""
    chapters: list[ChapterIn] = []

    def _split_window(texts: list[str], depth: int) -> list[list[str]] | None:
        """Split a failed window into smaller halves covering the same text."""
        if depth >= MAX_WINDOW_SPLITS:
            return None
        if len(texts) > 1:
            mid = len(texts) // 2
            return [texts[:mid], texts[mid:]]
        if estimate_tokens(texts[0], chars_per_token) <= MIN_SPLIT_TOKENS:
            return None
        halves = split_text_windows(
            texts[0], max(MIN_SPLIT_TOKENS, limit // 2), chars_per_token, splitter, overlap_chars
        )
        if len(halves) < 2:
            return None
        return [[half] for half in halves]

    async def _process(
        texts: list[str], pending: ChapterDraft | None, depth: int, is_last: bool
    ) -> ChapterDraft | None:
        """Segment one window; returns the pending tail for the next unit."""
        nonlocal title, author
        try:
            book, truncated = await segment_text_detailed("\n".join(texts), pending)
        except WindowSegmentationError as exc:
            halves = _split_window(texts, depth)
            if halves is not None:
                for j, half in enumerate(halves):
                    pending = await _process(
                        half, pending, depth + 1, is_last and j == len(halves) - 1
                    )
                return pending
            # Atomic failure: buffer whatever survived so one bad window
            # can't sink the book.
            piece = exc.partial
            if piece is not None and pending is not None:
                piece = ChapterDraft(
                    chapter_index=pending.chapter_index,
                    title=pending.title or piece.title,
                    body=merge_continued_body(pending.body, piece.body),
                )
            if piece is None and pending is None:
                raise WindowSegmentationError(
                    f"{exc} (window {window_page_label(texts)})"
                ) from exc
            return piece if piece is not None else pending
        if not title and book.title:
            title = book.title
        if not author and book.author:
            author = book.author
        window_chapters = list(book.chapters)
        if pending is not None:
            if not window_chapters:
                # Model returned nothing usable: keep the buffered text for
                # the following window instead of dropping it.
                return pending
            first = window_chapters[0]
            window_chapters[0] = ChapterIn(
                chapter_index=first.chapter_index,
                title=first.title or pending.title,
                body=merge_continued_body(pending.body, first.body),
            )
        pending_out: ChapterDraft | None = None
        if not is_last and window_chapters:
            tail = window_chapters[-1]
            if truncated or not ends_complete(tail.body):
                pending_out = ChapterDraft(
                    chapter_index=tail.chapter_index, title=tail.title, body=tail.body
                )
                window_chapters.pop()
        for ch in window_chapters:
            chapters.append(
                ChapterIn(
                    chapter_index=len(chapters) + 1,
                    title=ch.title,
                    body=ch.body,
                )
            )
        return pending_out

    last_index = len(windows) - 1
    pending: ChapterDraft | None = None
    for i, window_pages in enumerate(windows):
        # Atomic failures with nothing to preserve raise with the page
        # range attached (see _process); anything survivable is buffered.
        pending = await _process(window_pages, pending, 0, i == last_index)
    if pending is not None:
        # Trailing buffered text with no following window: emit best-effort.
        chapters.append(
            ChapterIn(chapter_index=len(chapters) + 1, title=pending.title, body=pending.body)
        )
    return SegmentedBook(title=title, author=author, chapters=chapters)
