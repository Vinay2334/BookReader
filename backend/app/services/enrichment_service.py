import httpx

OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"


async def enrich_metadata(title: str, author: str) -> tuple[str, str]:
    """Return (cover_url, description) from the Open Library Search API."""
    params = {"title": title, "author": author, "limit": 1}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(OPEN_LIBRARY_SEARCH_URL, params=params)
            resp.raise_for_status()
            docs = resp.json().get("docs", [])
    except httpx.HTTPError:
        return "", ""
    if not docs:
        return "", ""
    doc = docs[0]
    cover_url = ""
    cover_id = doc.get("cover_i")
    if cover_id:
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
    first_sentence = doc.get("first_sentence")
    if isinstance(first_sentence, list):
        description = first_sentence[0] if first_sentence else ""
    else:
        description = first_sentence or ""
    return cover_url, description or ""
