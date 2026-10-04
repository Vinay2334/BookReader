"""Tests for storage-path helpers used by book deletion.

stdlib unittest only: run with
`python -m unittest discover -s tests -t .` from `backend/`.
"""
import unittest

from app.services.storage_paths import public_url_to_path

BUCKET = "audiobooks"
BASE = "https://xyz.supabase.co/storage/v1/object/public/audiobooks"


class PublicUrlToPathTest(unittest.TestCase):
    def test_standard_public_url(self):
        url = f"{BASE}/book-id/1-abc123.mp3"
        self.assertEqual(public_url_to_path(url, BUCKET), "book-id/1-abc123.mp3")

    def test_strips_query_and_fragment(self):
        url = f"{BASE}/book-id/2-def.mp3?token=abc#frag"
        self.assertEqual(public_url_to_path(url, BUCKET), "book-id/2-def.mp3")

    def test_other_bucket_returns_none(self):
        url = "https://xyz.supabase.co/storage/v1/object/public/covers/x.jpg"
        self.assertIsNone(public_url_to_path(url, BUCKET))

    def test_empty_and_bare_bucket(self):
        self.assertIsNone(public_url_to_path("", BUCKET))
        self.assertIsNone(public_url_to_path(f"{BASE}/", BUCKET))
        self.assertIsNone(public_url_to_path(f"{BASE}/book-id/1.mp3", ""))


if __name__ == "__main__":
    unittest.main()
