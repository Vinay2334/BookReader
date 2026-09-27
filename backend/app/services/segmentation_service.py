import json
import re

from ..deps import get_openai_client
from ..config import settings
from ..schemas import SegmentedBook


SYSTEM_PROMPT = (
    "You segment book front matter / table of contents into clean chapters. "
    "Strip headers, footers, and page numbers. "
    'Respond with a JSON object shaped like {"title": str, "author": str, '
    '"chapters": [{"chapter_index": int, "title": str, "body": str}]}.'
)

# gpt-4o-mini supports up to 16384 output tokens. The default budget can cut
# multi-chapter bodies off mid-string, which surfaces downstream as
# "Unterminated string ..." JSON errors — so request a large budget.
MAX_SEGMENTATION_TOKENS = 16000


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


async def segment_front_matter(front_matter_text: str) -> SegmentedBook:
    client = get_openai_client()
    for _ in range(2):
        completion = await client.chat.completions.create(
            model=settings.openai_segmentation_model,
            response_format={"type": "json_object"},
            max_tokens=MAX_SEGMENTATION_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": front_matter_text},
            ],
        )
        raw = completion.choices[0].message.content or "{}"
        book = _parse_or_salvage(raw)
        if book is not None:
            return book
        # Nothing usable at all (e.g. cut off after a few chars): the failure
        # is usually transient, so the loop retries the request once.
    raise ValueError(
        "Model returned truncated or invalid JSON with no complete chapters; "
        "try a book with a shorter table of contents or a smaller front-matter window."
    )
