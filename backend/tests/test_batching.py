"""Regression tests for full-book batch extraction + parallel TTS pipeline.

stdlib unittest only (no new test framework): run with
`python -m unittest discover -s tests` from `backend/`.
Covers `app.services.batching`, which is dependency-free on purpose.
"""
import unittest

from app.services.batching import (
    ChapterBuffer,
    ChapterDraft,
    PipelineProgress,
    decode_partial_json_string,
    ends_complete,
    estimate_tokens,
    extract_partial_chapter,
    merge_chapters,
    merge_continued_body,
    split_into_batches,
    split_pages_into_token_windows,
    split_text_chunks,
    split_text_windows,
    window_page_label,
)


class SplitIntoBatchesTest(unittest.TestCase):
    def test_whole_book_covered_no_page_cap(self):
        pages = [f"page {i}" for i in range(1, 61)]  # 60 pages > old 25 cap
        batches = split_into_batches(pages, 25)
        self.assertEqual([len(b) for b in batches], [25, 25, 10])
        flat = [p for b in batches for p in b]
        self.assertEqual(flat, pages)  # every page yielded exactly once

    def test_exact_multiple_and_single_page(self):
        self.assertEqual(len(split_into_batches(["a", "b"], 1)), 2)
        self.assertEqual(split_into_batches([], 25), [])

    def test_invalid_batch_size(self):
        with self.assertRaises(ValueError):
            split_into_batches(["a"], 0)


class MergeChaptersTest(unittest.TestCase):
    def test_renumbers_across_batches(self):
        batches = [
            [ChapterDraft(1, "A", "a"), ChapterDraft(2, "B", "b")],
            [ChapterDraft(1, "C", "c")],  # per-batch index restarts
        ]
        merged = merge_chapters(batches)
        self.assertEqual([c.chapter_index for c in merged], [1, 2, 3])
        self.assertEqual([c.title for c in merged], ["A", "B", "C"])

    def test_empty(self):
        self.assertEqual(merge_chapters([]), [])


class SplitTextChunksTest(unittest.TestCase):
    def test_respects_limit_on_sentence_boundaries(self):
        long_text = "Hello world. " * 500  # ~6500 chars
        chunks = split_text_chunks(long_text, 4000)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(len(c) <= 4000 for c in chunks))

    def test_empty_and_single_sentence(self):
        self.assertEqual(split_text_chunks("", 4000), [])
        self.assertEqual(split_text_chunks("Hello.", 4000), ["Hello."])

    def test_oversize_sentence_kept_whole(self):
        text = "x" * 5000 + ". Done."
        chunks = split_text_chunks(text, 4000)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("x"))


class PipelineProgressTest(unittest.TestCase):
    def test_parallel_workers_progress(self):
        progress = PipelineProgress(
            total=3,
            chapters=[
                ChapterDraft(1, "A", "a"),
                ChapterDraft(2, "B", "b"),
                ChapterDraft(3, "C", "c"),
            ],
        )
        # Workers finish out of order (chapter 2 before chapter 1).
        progress.mark_done(2, "url-2")
        progress.mark_failed(1, "boom")
        progress.mark_done(3, "url-3")
        self.assertEqual(progress.done, 2)
        self.assertEqual(progress.failed, 1)
        by_index = {c.chapter_index: c for c in progress.chapters}
        self.assertEqual(by_index[2].audio_url, "url-2")
        self.assertEqual(by_index[1].error, "boom")


class EstimateTokensTest(unittest.TestCase):
    def test_scales_with_chars_per_token(self):
        self.assertEqual(estimate_tokens("x" * 40, 4.0), 10 + 1)
        self.assertEqual(estimate_tokens("", 4.0), 0)
        with self.assertRaises(ValueError):
            estimate_tokens("abc", 0)


class EndsCompleteTest(unittest.TestCase):
    def test_terminal_punctuation(self):
        self.assertTrue(ends_complete("It ended well."))
        self.assertTrue(ends_complete("Really?"))
        self.assertTrue(ends_complete('He said "go!"'))
        self.assertTrue(ends_complete("Trailing ellipsis…"))

    def test_truncated_mid_sentence(self):
        self.assertFalse(ends_complete("It ended in the midd"))
        self.assertFalse(ends_complete("Chapter text cut off, with a comma,"))
        self.assertFalse(ends_complete("No terminal here"))

    def test_empty_is_complete(self):
        self.assertTrue(ends_complete(""))
        self.assertTrue(ends_complete("   "))


class SplitTextWindowsTest(unittest.TestCase):
    def test_windows_respect_token_budget(self):
        text = "First sentence here. Second sentence here. Third one here. Fourth here."
        windows = split_text_windows(text, 10, 4.0)
        self.assertGreaterEqual(len(windows), 2)
        for w in windows:
            self.assertLessEqual(estimate_tokens(w, 4.0), 10)
        # Reassembled in order, nothing lost.
        self.assertEqual(" ".join(windows), text)

    def test_oversize_sentence_own_window(self):
        text = "Short. " + "y" * 500 + ". After."
        windows = split_text_windows(text, 10, 4.0)
        self.assertGreaterEqual(len(windows), 2)

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            split_text_windows("abc", 0)


class SplitPagesIntoTokenWindowsTest(unittest.TestCase):
    def test_whole_book_covered_in_order(self):
        pages = [f"Page {i} content here. More text here." for i in range(1, 21)]
        windows = split_pages_into_token_windows(pages, 20, 4.0)
        flat = [p for w in windows for p in w]
        self.assertEqual(flat, pages)  # every page yielded exactly once
        for w in windows:
            self.assertLessEqual(estimate_tokens(" ".join(w), 4.0), 20)

    def test_max_pages_cap(self):
        pages = ["a. b. c." for _ in range(10)]
        windows = split_pages_into_token_windows(pages, 10_000, 4.0, max_pages=3)
        self.assertEqual([len(w) for w in windows], [3, 3, 3, 1])

    def test_oversize_page_sentence_split(self):
        big = "Sentence one here. " + "z" * 500 + ". Sentence three here."
        windows = split_pages_into_token_windows(["ok page.", big], 20, 4.0)
        self.assertEqual(windows[0], ["ok page."])
        self.assertGreaterEqual(len(windows), 3)
        self.assertIn("Sentence three here.", windows[-1][0])

    def test_invalid_args(self):
        with self.assertRaises(ValueError):
            split_pages_into_token_windows(["a"], 0)
        with self.assertRaises(ValueError):
            split_pages_into_token_windows(["a"], 10, max_pages=-1)


class MergeContinuedBodyTest(unittest.TestCase):
    def test_disjoint_parts_concatenated(self):
        self.assertEqual(
            merge_continued_body("The story so far", "and then it ended."),
            "The story so far and then it ended.",
        )

    def test_echoed_body_not_duplicated(self):
        pending = "The story so far and"
        full = "The story so far and then it ended."
        self.assertEqual(merge_continued_body(pending, full), full)

    def test_empty_sides(self):
        self.assertEqual(merge_continued_body("", "next"), "next")
        self.assertEqual(merge_continued_body("pending", ""), "pending")


class ChapterBufferTest(unittest.TestCase):
    def test_hold_take_roundtrip(self):
        buf = ChapterBuffer()
        self.assertIsNone(buf.take())
        buf.hold(ChapterDraft(2, "Middle", "cut off mid-"))
        held = buf.take()
        self.assertIsNotNone(held)
        assert held is not None
        self.assertEqual(held.title, "Middle")
        self.assertEqual(held.body, "cut off mid-")
        self.assertIsNone(buf.take())  # take drains

    def test_double_hold_never_drops_text(self):
        buf = ChapterBuffer()
        buf.hold(ChapterDraft(1, "A", "first part"))
        buf.hold(ChapterDraft(1, "A", "second part."))
        held = buf.take()
        assert held is not None
        self.assertIn("first part", held.body)
        self.assertIn("second part.", held.body)


class UnknownSplitterTest(unittest.TestCase):
    def test_rejects_unknown_splitter(self):
        with self.assertRaises(ValueError):
            split_text_chunks("hello.", 100, splitter="nope")
        with self.assertRaises(ValueError):
            split_text_windows("hello.", 100, splitter="nope")


class DecodePartialJsonStringTest(unittest.TestCase):
    def test_terminated_string(self):
        self.assertEqual(decode_partial_json_string('"hello world"', 0), "hello world")

    def test_unterminated_string_returns_so_far(self):
        self.assertEqual(decode_partial_json_string('"hello wor', 0), "hello wor")

    def test_dangling_escape_dropped(self):
        self.assertEqual(decode_partial_json_string('"hello\\', 0), "hello")

    def test_escapes_preserved(self):
        self.assertEqual(
            decode_partial_json_string('"say \\"hi\\". Talk', 0), 'say "hi". Talk'
        )


class ExtractPartialChapterTest(unittest.TestCase):
    # Mirrors the reported failure: output cut inside the first chapter body.
    TRUNCATED = (
        '{"title": "Harry Potter", "author": "J. K. Rowling", "chapters": ['
        '{"chapter_index": 1, "title": "The Boy Who Lived", '
        '"body": "Mr and Mrs Dursley of number four, Privet Drive, were proud '
        "to say that they were perfectly normal, thank you very mu"
    )

    def test_recovers_partial_first_chapter(self):
        partial = extract_partial_chapter(self.TRUNCATED)
        self.assertIsNotNone(partial)
        assert partial is not None
        self.assertEqual(partial.chapter_index, 1)
        self.assertEqual(partial.title, "The Boy Who Lived")
        self.assertTrue(partial.body.startswith("Mr and Mrs Dursley"))

    def test_no_chapter_returns_none(self):
        self.assertIsNone(extract_partial_chapter('{"title": "x", "author": "y"}'))
        self.assertIsNone(extract_partial_chapter("not json at all"))
        self.assertIsNone(extract_partial_chapter(""))

    def test_title_without_body_still_recovered(self):
        raw = '{"chapters": [{"chapter_index": 2, "title": "Halfway", "body": "'
        partial = extract_partial_chapter(raw)
        self.assertIsNotNone(partial)
        assert partial is not None
        self.assertEqual(partial.chapter_index, 2)
        self.assertEqual(partial.title, "Halfway")


class WindowPageLabelTest(unittest.TestCase):
    def test_range_and_single(self):
        self.assertEqual(
            window_page_label(["\n\n===== PAGE 3 =====\nabc", "\n\n===== PAGE 5 =====\ndef"]),
            "pages 3-5",
        )
        self.assertEqual(window_page_label(["\n\n===== PAGE 7 =====\nabc"]), "page 7")

    def test_no_markers(self):
        self.assertEqual(window_page_label(["a", "b"]), "2 page(s)")


if __name__ == "__main__":
    unittest.main()
