import { create } from "zustand";

export type PlaybackStatus = "playing" | "paused" | "buffering";

export type ActiveTrack = {
  episodeId: string;
  bookId: string;
  bookTitle: string;
  chapterTitle: string;
  audioUrl: string;
};

type PlayerState = {
  track: ActiveTrack | null;
  status: PlaybackStatus;
  currentTime: number;
  duration: number;
  volume: number;
  rate: number;
  play: (track: ActiveTrack) => void;
  pause: () => void;
  resume: () => void;
  setStatus: (status: PlaybackStatus) => void;
  setCurrentTime: (t: number) => void;
  setDuration: (d: number) => void;
  setVolume: (v: number) => void;
  setRate: (r: number) => void;
};

export const SPEEDS = [0.75, 1, 1.25, 1.5, 2];

export const usePlayerStore = create<PlayerState>((set) => ({
  track: null,
  status: "paused",
  currentTime: 0,
  duration: 0,
  volume: 1,
  rate: 1,
  play: (track) => set({ track, status: "playing", currentTime: 0 }),
  pause: () => set({ status: "paused" }),
  resume: () => set({ status: "playing" }),
  setStatus: (status) => set({ status }),
  setCurrentTime: (t) => set({ currentTime: t }),
  setDuration: (d) => set({ duration: d }),
  setVolume: (v) => set({ volume: v }),
  setRate: (r) => set({ rate: r }),
}));
