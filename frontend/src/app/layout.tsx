import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "job-fit-agent",
  description: "A resume tailoring tool that won't let you lie: every claim is linked to its evidence.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col font-sans">
        <Nav />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">{children}</main>
        <footer className="py-6 text-center text-xs text-slate-400">
          Runs locally · your resume never leaves your machine except for the LLM calls you configure
        </footer>
      </body>
    </html>
  );
}
