"use client";

import { useState } from "react";
import { ChevronDown, Play } from "lucide-react";
import type { Episode } from "@/lib/api";
import { usePlayerStore } from "@/store/player-store";

function formatDuration(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function ChapterList({
  bookId,
  bookTitle,
  episodes,
}: {
  bookId: string;
  bookTitle: string;
  episodes: Episode[];
}) {
  const [openId, setOpenId] = useState<string | null>(null);
  const play = usePlayerStore((s) => s.play);
  const activeId = usePlayerStore((s) => s.track?.episodeId);

  if (episodes.length === 0) {
    return <p className="mt-3 text-sm text-zinc-500">No chapters yet — audio is still generating.</p>;
  }

  return (
    <ul className="mt-3 divide-y divide-zinc-100 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
      {episodes.map((ep) => {
        const open = openId === ep.id;
        return (
          <li key={ep.id}>
            <button
              onClick={() => setOpenId(open ? null : ep.id)}
              className="flex w-full items-center gap-3 px-4 py-3 text-left"
            >
              <ChevronDown
                className={`h-4 w-4 shrink-0 text-zinc-400 transition-transform ${open ? "" : "-rotate-90"}`}
              />
              <span className="mr-1 text-sm font-medium text-zinc-400">{ep.episode_number}.</span>
              <span className="flex-1 truncate text-sm font-medium">{ep.title}</span>
              {ep.duration > 0 && (
                <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                  {formatDuration(ep.duration)}
                </span>
              )}
              {activeId === ep.id && (
                <span className="rounded-full bg-zinc-900 px-2.5 py-0.5 text-xs text-white dark:bg-zinc-100 dark:text-zinc-900">
                  Now playing
                </span>
              )}
            </button>
            {open && (
              <div className="px-4 pb-4 pl-11">
                <button
                  disabled={!ep.audio_url}
                  onClick={() =>
                    play({
                      episodeId: ep.id,
                      bookId,
                      bookTitle,
                      chapterTitle: ep.title,
                      audioUrl: ep.audio_url,
                    })
                  }
                  className="inline-flex items-center gap-2 rounded-full border border-zinc-300 px-4 py-1.5 text-sm font-medium disabled:opacity-40 dark:border-zinc-700"
                >
                  <Play className="h-3.5 w-3.5" />
                  {ep.audio_url ? "Play chapter" : "Audio pending"}
                </button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
