"""Storage-path helpers for the audiobooks bucket.

stdlib only, so this module and its tests run anywhere without backend
dependencies. Used when deleting a book to map stored public URLs back
to in-bucket paths.
"""
from __future__ import annotations

from urllib.parse import unquote, urlsplit


def public_url_to_path(public_url: str, bucket: str) -> str | None:
    """Extract the in-bucket path from a Supabase public file URL.

    e.g. ``https://xyz.supabase.co/storage/v1/object/public/audiobooks/<book>/<file>.mp3``
    with bucket ``audiobooks`` -> ``<book>/<file>.mp3``.
    Returns None when the URL is empty, belongs to another bucket, or has
    no path remainder.
    """
    if not public_url or not bucket:
        return None
    marker = f"/{bucket.strip('/')}/"
    remainder = urlsplit(public_url).path
    idx = remainder.find(marker)
    if idx == -1:
        return None
    path = unquote(remainder[idx + len(marker):]).strip("/")
    return path or None
