"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft, Play } from "lucide-react";
import { ChapterList } from "@/components/ChapterList";
import { getBook } from "@/lib/api";
import { usePlayerStore } from "@/store/player-store";

function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function BookDetailPage({ params }: { params: { id: string } }) {
  const { data: book, isLoading, isError } = useQuery({
    queryKey: ["book", params.id],
    queryFn: () => getBook(params.id),
  });
  const play = usePlayerStore((s) => s.play);

  if (isLoading) return <p className="text-sm text-zinc-500">Loading book…</p>;
  if (isError || !book) return <p className="text-sm text-red-500">Book not found.</p>;

  const firstPlayable = book.episodes.find((e) => e.audio_url);
  const totalSeconds = book.episodes.reduce((sum, e) => sum + (e.duration || 0), 0);

  return (
    <div>
      <Link
        href="/"
        className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100"
      >
        <ArrowLeft className="h-4 w-4" /> Back to library
      </Link>

      <div className="mt-6 grid gap-8 md:grid-cols-[240px_1fr]">
        <div>
          {book.cover_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={book.cover_url}
              alt={`${book.title} cover`}
              className="aspect-[2/3] w-full rounded-xl border border-zinc-200 object-cover shadow-sm dark:border-zinc-800"
            />
          ) : (
            <div className="flex aspect-[2/3] w-full items-center justify-center rounded-xl border border-dashed border-zinc-300 text-4xl font-semibold text-zinc-300 dark:border-zinc-700">
              {book.title.charAt(0)}
            </div>
          )}
        </div>

        <div>
          <span className="inline-flex items-center rounded-full border border-zinc-200 px-3 py-1 text-xs font-medium text-zinc-600 dark:border-zinc-800 dark:text-zinc-300">
            {book.total_chapters} chapters · {formatDuration(totalSeconds)}
          </span>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">{book.title}</h1>
          {book.author && <p className="mt-1 text-sm text-zinc-500">by {book.author}</p>}
          {book.description && (
            <p className="mt-4 max-w-2xl text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
              {book.description}
            </p>
          )}
          <button
            disabled={!firstPlayable}
            onClick={() =>
              firstPlayable &&
              play({
                episodeId: firstPlayable.id,
                bookId: book.id,
                bookTitle: book.title,
                chapterTitle: firstPlayable.title,
                audioUrl: firstPlayable.audio_url,
              })
            }
            className="mt-6 inline-flex items-center gap-2 rounded-full bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
          >
            <Play className="h-4 w-4" /> Listen Now
          </button>
        </div>
      </div>

      <div className="mt-10">
        <h2 className="text-lg font-semibold">Chapters</h2>
        <ChapterList
          bookId={book.id}
          bookTitle={book.title}
          episodes={book.episodes}
        />
      </div>
    </div>
  );
}
