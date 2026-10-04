"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2, X } from "lucide-react";
import {
  extractPdf,
  generateAudio,
  getAudioJob,
  persistFromExtraction,
  type ExtractionJob,
  type ExtractionPreview,
} from "@/lib/api";

type Step = 1 | 2 | 3;

export function UploadWizard({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<Step>(1);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ExtractionPreview | null>(null);
  const [bookId, setBookId] = useState<string | null>(null);
  const [extractJob, setExtractJob] = useState<ExtractionJob | null>(null);
  const [audioJobId, setAudioJobId] = useState<string | null>(null);
  const [error, setError] = useState<string>("");
  const queryClient = useQueryClient();

  const extractMutation = useMutation({
    mutationFn: (f: File) => extractPdf(f, setExtractJob),
    onSuccess: (data) => {
      setPreview(data);
      setStep(2);
    },
    onError: (e) =>
      setError(
        e instanceof Error && e.message
          ? e.message
          : "Extraction failed. Check the API connection and try again.",
      ),
  });

  const audioJobQuery = useQuery({
    queryKey: ["audio-job", audioJobId],
    queryFn: () => getAudioJob(audioJobId as string),
    enabled: step === 3 && audioJobId !== null,
    refetchInterval: (data) => {
      const s = data?.status;
      return s === "done" || s === "failed" || s === "cancelled" ? false : 2000;
    },
  });

  const publishMutation = useMutation({
    mutationFn: async () => {
      if (!preview) throw new Error("Nothing to publish");
      // Chapters stay backend-side: persist + synthesize by extraction job id.
      const saved = await persistFromExtraction(preview.jobId);
      setBookId(saved.book.id);
      const job = await generateAudio(saved.book.id);
      setAudioJobId(job.job_id);
      return saved;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["books"] });
      setStep(3);
    },
    onError: () => setError("Publishing failed. Please try again."),
  });

  const busy = extractMutation.isPending || publishMutation.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-zinc-200 bg-white p-6 shadow-lg dark:border-zinc-800 dark:bg-zinc-900">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            {step === 1 && "Upload a PDF"}
            {step === 2 && "Review chapters"}
            {step === 3 && "Audio generation started"}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <ol className="mt-4 flex items-center gap-2 text-xs font-medium">
          {(["Upload", "Review", "Generate"] as const).map((label, i) => (
            <li key={label} className="flex items-center gap-2">
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full border ${
                  step > i
                    ? "border-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900"
                    : "border-zinc-300 text-zinc-500 dark:border-zinc-700"
                }`}
              >
                {i + 1}
              </span>
              {label}
              {i < 2 && <span className="mx-1 h-px w-6 bg-zinc-200 dark:bg-zinc-700" />}
            </li>
          ))}
        </ol>

        {error && <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-600">{error}</p>}

        {step === 1 && (
          <div className="mt-6">
            <label
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const f = e.dataTransfer.files?.[0];
                if (f) setFile(f);
              }}
              className="flex cursor-pointer flex-col items-center rounded-xl border border-dashed border-zinc-300 px-6 py-12 text-center dark:border-zinc-700"
            >
              <FileUp className="h-8 w-8 text-zinc-400" />
              <p className="mt-3 text-sm font-medium">
                {file ? file.name : "Drag & drop your PDF here"}
              </p>
              <p className="mt-1 text-xs text-zinc-500">or click to browse files</p>
              <input
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <button
              disabled={!file || busy}
              onClick={() => {
                setError("");
                setExtractJob(null);
                if (file) extractMutation.mutate(file);
              }}
              className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-full bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
            >
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              Extract chapters
            </button>
            {extractMutation.isPending && (
              <p className="mt-3 text-center text-xs text-zinc-500">
                {extractJob && extractJob.num_pages > 0
                  ? `Parsing full book (${extractJob.num_pages} pages) and segmenting chapters…`
                  : "Uploading and starting background extraction…"}
              </p>
            )}
          </div>
        )}

        {step === 2 && preview && (
          <div className="mt-6">
            <div className="flex gap-4">
              {preview.cover_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={preview.cover_url}
                  alt="Detected cover art"
                  className="h-28 w-20 rounded-lg border border-zinc-200 object-cover dark:border-zinc-700"
                />
              )}
              <div>
                <p className="text-base font-semibold">{preview.title || "Untitled"}</p>
                {preview.author && <p className="text-sm text-zinc-500">{preview.author}</p>}
                {preview.description && (
                  <p className="mt-2 line-clamp-3 text-sm text-zinc-600 dark:text-zinc-300">
                    {preview.description}
                  </p>
                )}
                <span className="mt-2 inline-flex items-center rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                  {preview.chapters.length} chapters detected
                </span>
              </div>
            </div>
            <ul className="mt-4 divide-y divide-zinc-100 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
              {preview.chapters.map((ch) => (
                <li key={ch.chapter_index} className="px-4 py-2.5 text-sm">
                  <span className="mr-2 font-medium text-zinc-400">{ch.chapter_index}.</span>
                  {ch.title}
                </li>
              ))}
            </ul>
            <button
              disabled={busy}
              onClick={() => publishMutation.mutate()}
              className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-full bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
            >
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              Generate audio
            </button>
          </div>
        )}

        {step === 3 && (
          <div className="mt-6 text-center">
            {(() => {
              const job = audioJobQuery.data;
              const total = job?.total_chapters ?? preview?.chapters.length ?? 0;
              const done = job?.done_chapters ?? 0;
              const pct = total > 0 ? Math.round((done / total) * 100) : 0;
              return (
                <>
                  <p className="text-sm text-zinc-600 dark:text-zinc-300">
                    {job?.status === "done"
                      ? `All ${total} chapters have audio.`
                      : job?.status === "failed"
                        ? `Audio generation stopped: ${job.error || "a chapter failed."}`
                        : job?.status === "cancelled"
                          ? "Audio generation was cancelled."
                          : `Generating audio in parallel — ${done} of ${total} chapters done.`}
                    {bookId && " You can open it from your library once chapters finish."}
                  </p>
                  <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                    <div
                      className="h-full rounded-full bg-zinc-900 transition-all dark:bg-zinc-100"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  {(job?.failed_chapters ?? 0) > 0 && (
                    <p className="mt-2 text-xs text-red-500">
                      {job?.failed_chapters} chapter(s) failed to synthesize.
                    </p>
                  )}
                </>
              );
            })()}
            <button
              onClick={onClose}
              className="mt-5 inline-flex items-center justify-center rounded-full border border-zinc-300 px-5 py-2 text-sm font-medium dark:border-zinc-700"
            >
              Back to library
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
