"use client";

import Link from "next/link";
import type { Book } from "@/lib/api";

export function BookCard({ book }: { book: Book }) {
  return (
    <Link
      href={`/books/${book.id}`}
      className="group overflow-hidden rounded-xl border border-zinc-200 bg-white transition-shadow hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900"
    >
      <div className="aspect-[2/3] w-full bg-zinc-100 dark:bg-zinc-800">
        {book.cover_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={book.cover_url}
            alt={`${book.title} cover`}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-4xl font-semibold text-zinc-300 dark:text-zinc-600">
            {book.title.charAt(0)}
          </div>
        )}
      </div>
      <div className="p-4">
        <h3 className="truncate text-sm font-semibold">{book.title}</h3>
        {book.author && (
          <span className="mt-2 inline-flex items-center rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
            {book.author}
          </span>
        )}
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          {book.total_chapters} chapters
        </p>
      </div>
    </Link>
  );
}
