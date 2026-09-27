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

export type ExtractionPreview = {
  filename: string;
  title: string;
  author: string;
  cover_url: string;
  description: string;
  chapters: ChapterDraft[];
};

export async function listBooks(): Promise<Book[]> {
  const { data } = await api.get("/api/books");
  return data;
}

export async function getBook(id: string): Promise<BookDetail> {
  const { data } = await api.get(`/api/books/${id}`);
  return data;
}

export async function extractPdf(file: File): Promise<ExtractionPreview> {
  const form = new FormData();
  form.append("file", file);
  await api.post("/api/books/extract", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  const { data } = await api.get("/api/books/extract/preview");
  return data;
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

export async function generateAudio(
  bookId: string,
  chapters: ChapterDraft[],
  title: string,
  author: string,
): Promise<{ book_id: string; episodes: Episode[] }> {
  // return Promise.resolve({ book_id: bookId, episodes: [] });
  const { data } = await api.post(`/api/books/${bookId}/generate-audio`, {
    title,
    author,
    chapters,
  });
  return data;
}
