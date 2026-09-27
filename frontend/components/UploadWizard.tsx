"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2, X } from "lucide-react";
import { extractPdf, generateAudio, persistBook, type ExtractionPreview } from "@/lib/api";

type Step = 1 | 2 | 3;

export function UploadWizard({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState<Step>(1);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ExtractionPreview | null>(null);
  const [bookId, setBookId] = useState<string | null>(null);
  const [error, setError] = useState<string>("");
  const queryClient = useQueryClient();

  const extractMutation = useMutation({
    mutationFn: (f: File) => extractPdf(f),
    onSuccess: (data) => {
      setPreview(data);
      setStep(2);
    },
    onError: () => setError("Extraction failed. Check the API connection and try again."),
  });

  const publishMutation = useMutation({
    mutationFn: async () => {
      if (!preview) throw new Error("Nothing to publish");
      const saved = await persistBook({
        title: preview.title,
        author: preview.author,
        description: preview.description,
        cover_url: preview.cover_url,
        chapters: preview.chapters,
      });
      setBookId(saved.book.id);
      await generateAudio(saved.book.id, preview.chapters, preview.title, preview.author);
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
              onClick={() => file && extractMutation.mutate(file)}
              className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-full bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
            >
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              Extract chapters
            </button>
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
            <p className="text-sm text-zinc-600 dark:text-zinc-300">
              Your audiobook is being generated in the background.
              {bookId && " You can open it from your library once chapters finish."}
            </p>
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
