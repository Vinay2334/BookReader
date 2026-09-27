"use client";

import { Search, Upload } from "lucide-react";
import { BookCard } from "./BookCard";
import type { Book } from "@/lib/api";

export function BookGrid({
  books,
  loading,
  error,
  searchQuery,
  onSearchChange,
  onUpload,
}: {
  books: Book[];
  loading: boolean;
  error: boolean;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onUpload: () => void;
}) {
  return (
    <div>
      <div className="relative mb-5 max-w-sm">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
        <input
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search title or author…"
          className="w-full rounded-full border border-zinc-200 bg-zinc-50 py-2 pl-9 pr-3 text-sm outline-none placeholder:text-zinc-400 focus:border-zinc-400 dark:border-zinc-800 dark:bg-zinc-900"
        />
      </div>

      {loading && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="aspect-[2/3] animate-pulse rounded-xl bg-zinc-100 dark:bg-zinc-800"
            />
          ))}
        </div>
      )}

      {!loading && error && <p className="text-sm text-red-500">Could not load your library.</p>}

      {!loading && !error && books.length === 0 && (
        <div className="flex flex-col items-center rounded-xl border border-dashed border-zinc-300 px-6 py-16 text-center dark:border-zinc-700">
          <p className="text-base font-medium">
            {searchQuery ? "No matches found" : "No audiobooks yet"}
          </p>
          <p className="mt-1 max-w-sm text-sm text-zinc-500 dark:text-zinc-400">
            {searchQuery
              ? "Try a different title or author."
              : "Upload your first PDF to generate chapters and audio."}
          </p>
          {!searchQuery && (
            <button
              onClick={onUpload}
              className="mt-5 inline-flex items-center gap-2 rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
            >
              <Upload className="h-4 w-4" /> Upload Book
            </button>
          )}
        </div>
      )}

      {!loading && !error && books.length > 0 && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {books.map((book) => (
            <BookCard key={book.id} book={book} />
          ))}
        </div>
      )}
    </div>
  );
}
