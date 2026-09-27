"use client";

import { useEffect, useRef } from "react";
import { Pause, Play, RotateCcw, RotateCw } from "lucide-react";
import { SPEEDS, usePlayerStore } from "@/store/player-store";

function formatTime(totalSeconds: number): string {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return "0:00";
  const m = Math.floor(totalSeconds / 60);
  const s = Math.floor(totalSeconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function AudioPlayer() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const track = usePlayerStore((s) => s.track);
  const status = usePlayerStore((s) => s.status);
  const currentTime = usePlayerStore((s) => s.currentTime);
  const duration = usePlayerStore((s) => s.duration);
  const volume = usePlayerStore((s) => s.volume);
  const rate = usePlayerStore((s) => s.rate);
  const { pause, resume, setStatus, setCurrentTime, setDuration, setVolume, setRate } =
    usePlayerStore.getState();

  useEffect(() => {
    const el = audioRef.current;
    if (!el || !track) return;
    el.src = track.audioUrl;
    el.playbackRate = usePlayerStore.getState().rate;
    el.volume = usePlayerStore.getState().volume;
    setStatus("buffering");
    el.play().then(
      () => setStatus("playing"),
      () => setStatus("paused"),
    );
  }, [track, setStatus]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    if (status === "playing" && el.paused && track) {
      el.play().catch(() => setStatus("paused"));
    } else if (status === "paused" && !el.paused) {
      el.pause();
    }
  }, [status, track, setStatus]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = rate;
  }, [rate]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.volume = volume;
  }, [volume]);

  if (!track) return null;

  const skip = (delta: number) => {
    const el = audioRef.current;
    if (!el) return;
    el.currentTime = Math.min(Math.max(0, el.currentTime + delta), el.duration || 0);
  };

  const cycleSpeed = () => {
    const next = SPEEDS[(SPEEDS.indexOf(rate) + 1) % SPEEDS.length];
    setRate(next);
  };

  return (
    <div className="fixed inset-x-0 bottom-4 z-50 mx-auto w-[calc(100%-2rem)] max-w-3xl">
      <div className="rounded-full border border-zinc-200 bg-white/95 py-2 pl-4 pr-3 shadow-lg backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/95">
        <audio
          ref={audioRef}
          onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
          onWaiting={() => setStatus("buffering")}
          onPlaying={() => setStatus("playing")}
          onPause={() => {
            if (usePlayerStore.getState().status === "playing") setStatus("paused");
          }}
          onEnded={() => setStatus("paused")}
        />
        <div className="flex items-center gap-2 sm:gap-3">
          <button
            onClick={() => skip(-15)}
            aria-label="Back 15 seconds"
            className="rounded-full p-2 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <RotateCcw className="h-4 w-4" />
          </button>
          <button
            onClick={() => (status === "playing" ? pause() : resume())}
            aria-label={status === "playing" ? "Pause" : "Play"}
            className="rounded-full bg-zinc-900 p-2.5 text-white dark:bg-zinc-100 dark:text-zinc-900"
          >
            {status === "playing" || status === "buffering" ? (
              <Pause className="h-4 w-4" />
            ) : (
              <Play className="h-4 w-4" />
            )}
          </button>
          <button
            onClick={() => skip(15)}
            aria-label="Forward 15 seconds"
            className="rounded-full p-2 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
          >
            <RotateCw className="h-4 w-4" />
          </button>

          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-medium">
              {track.chapterTitle}
              <span className="ml-2 font-normal text-zinc-500">{track.bookTitle}</span>
            </p>
            <div className="flex items-center gap-2">
              <span className="text-[11px] tabular-nums text-zinc-500">{formatTime(currentTime)}</span>
              <input
                type="range"
                min={0}
                max={duration || 0}
                step={0.1}
                value={currentTime}
                onChange={(e) => {
                  const el = audioRef.current;
                  const t = Number(e.target.value);
                  if (el) el.currentTime = t;
                  setCurrentTime(t);
                }}
                className="w-full"
                aria-label="Seek"
              />
              <span className="text-[11px] tabular-nums text-zinc-500">{formatTime(duration)}</span>
            </div>
          </div>

          <button
            onClick={cycleSpeed}
            className="rounded-full border border-zinc-200 px-2.5 py-1 text-xs font-medium tabular-nums dark:border-zinc-700"
            aria-label="Playback speed"
          >
            {rate}x
          </button>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={volume}
            onChange={(e) => setVolume(Number(e.target.value))}
            className="hidden w-20 sm:block"
            aria-label="Volume"
          />
        </div>
      </div>
    </div>
  );
}
