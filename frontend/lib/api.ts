import axios from "axios";

const baseURL = process.env.NEXT_PUBLIC_FASTAPI_BASE_URL ?? "http://localhost:8000";

export const api = axios.create({ baseURL });

export type Episode = {
  id: string;
  book_id: string;
  episode_number: number;
  title: string;
  duration: number;
  audio_url: string;
};

export type Book = {
  id: string;
  title: string;
  author: string;
  description: string;
  cover_url: string;
  total_chapters: number;
};

export type BookDetail = Book & { episodes: Episode[] };

export type ChapterDraft = { chapter_index: number; title: string; body: string };

export type ChapterPreview = { chapter_index: number; title: string };

export type ExtractionPreview = {
  jobId: string;
  filename: string;
  title: string;
  author: string;
  cover_url: string;
  description: string;
  chapters: ChapterPreview[];
};

export async function listBooks(): Promise<Book[]> {
  const { data } = await api.get("/api/books");
  return data;
}

export async function getBook(id: string): Promise<BookDetail> {
  const { data } = await api.get(`/api/books/${id}`);
  return data;
}

export type ExtractionJob = {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  filename: string;
  num_pages: number;
  total_chapters: number;
  title: string;
  author: string;
  cover_url: string;
  description: string;
  chapters: ChapterPreview[];
  error: string;
};

export type AudioJob = {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  book_id: string;
  total_chapters: number;
  done_chapters: number;
  failed_chapters: number;
  error: string;
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function extractPdf(
  file: File,
  onProgress?: (job: ExtractionJob) => void,
): Promise<ExtractionPreview> {
  const form = new FormData();
  form.append("file", file);
  const { data: job } = await api.post<ExtractionJob>("/api/books/extract", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  for (;;) {
    const { data: current } = await api.get<ExtractionJob>(
      `/api/books/extract/jobs/${job.job_id}`,
    );
    onProgress?.(current);
    if (current.status === "done") {
      return {
        jobId: current.job_id,
        filename: current.filename,
        title: current.title,
        author: current.author,
        cover_url: current.cover_url,
        description: current.description,
        chapters: current.chapters,
      };
    }
    if (current.status === "failed") {
      throw new Error(current.error || "Extraction failed in the background job.");
    }
    await sleep(1500);
  }
}

export async function persistBook(payload: {
  title: string;
  author: string;
  description: string;
  cover_url: string;
  chapters: ChapterDraft[];
}): Promise<{ book: Book; episodes: Episode[] }> {
  const { data } = await api.post("/api/books", payload);
  return data;
}

export async function persistFromExtraction(
  jobId: string,
): Promise<{ book: Book; episodes: Episode[] }> {
  const { data } = await api.post("/api/books/from-extraction", { job_id: jobId });
  return data;
}

export async function generateAudio(bookId: string): Promise<AudioJob> {
  const { data } = await api.post<AudioJob>(`/api/books/${bookId}/generate-audio`);
  return data;
}

export async function getAudioJob(jobId: string): Promise<AudioJob> {
  const { data } = await api.get<AudioJob>(`/api/books/audio/jobs/${jobId}`);
  return data;
}

export async function deleteBook(
  id: string,
): Promise<{ book_id: string; removed_files: number }> {
  const { data } = await api.delete(`/api/books/${id}`);
  return data;
}
