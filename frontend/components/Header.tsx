"use client";

import Link from "next/link";
import { BookOpenText, Upload } from "lucide-react";

export const OPEN_UPLOAD_EVENT = "bookreader:open-upload";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-zinc-200 bg-white/80 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/80">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2">
          <BookOpenText className="h-5 w-5" />
          <span className="text-base font-semibold tracking-tight">BookReader</span>
        </Link>
        <button
          onClick={() => window.dispatchEvent(new CustomEvent(OPEN_UPLOAD_EVENT))}
          className="ml-auto inline-flex items-center gap-2 rounded-full bg-zinc-900 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
        >
          <Upload className="h-4 w-4" /> Upload Book
        </button>
      </div>
    </header>
  );
}
