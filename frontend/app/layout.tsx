import type { Metadata } from "next";
import "./globals.css";
import { AudioPlayer } from "@/components/AudioPlayer";
import { Header } from "@/components/Header";
import { QueryProvider } from "@/lib/query-provider";

export const metadata: Metadata = {
  title: "BookReader",
  description: "Turn PDFs into audiobooks",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <QueryProvider>
          <Header />
          <main className="mx-auto max-w-6xl px-4 pb-32 pt-6 sm:px-6">{children}</main>
          <AudioPlayer />
        </QueryProvider>
      </body>
    </html>
  );
}
