"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { BookGrid } from "@/components/BookGrid";
import { OPEN_UPLOAD_EVENT } from "@/components/Header";
import { UploadWizard } from "@/components/UploadWizard";
import { listBooks } from "@/lib/api";

export default function HomePage() {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [query, setQuery] = useState("");
  const booksQuery = useQuery({ queryKey: ["books"], queryFn: listBooks });

  useEffect(() => {
    const open = () => setWizardOpen(true);
    window.addEventListener(OPEN_UPLOAD_EVENT, open);
    return () => window.removeEventListener(OPEN_UPLOAD_EVENT, open);
  }, []);

  const books = (booksQuery.data ?? []).filter(
    (b) =>
      query === "" ||
      b.title.toLowerCase().includes(query.toLowerCase()) ||
      b.author.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div>
      <section className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">Your library</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Upload a PDF, review the chapters, and listen anywhere.
        </p>
      </section>
      <BookGrid
        books={books}
        loading={booksQuery.isLoading}
        error={booksQuery.isError}
        searchQuery={query}
        onSearchChange={setQuery}
        onUpload={() => setWizardOpen(true)}
      />
      {wizardOpen && <UploadWizard onClose={() => setWizardOpen(false)} />}
    </div>
  );
}
