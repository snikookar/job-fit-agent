"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api } from "@/lib/api";

export default function NewJobPage() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await api.startJob({ url: url.trim() || undefined, text: text.trim() || undefined });
      router.push(`/jobs/${run_id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Analyze a job posting" subtitle="Paste the text (most reliable) or a link to a public posting." />
      <form onSubmit={submit} className="card space-y-5">
        <div>
          <label className="label" htmlFor="text">Job description</label>
          <textarea
            id="text"
            className="input min-h-72 font-mono text-xs leading-relaxed"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"# Senior Backend Engineer\n\n## Requirements\n- 5+ years of Python\n- ..."}
          />
        </div>
        <div className="flex items-center gap-3 text-xs uppercase tracking-wide text-slate-400">
          <span className="h-px flex-1 bg-slate-200" /> or <span className="h-px flex-1 bg-slate-200" />
        </div>
        <div>
          <label className="label" htmlFor="url">Link to the posting</label>
          <input
            id="url"
            className="input"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://boards.greenhouse.io/company/jobs/123"
          />
          <p className="mt-1.5 text-xs text-slate-500">
            Greenhouse, Lever and Personio are read through their public APIs; other career pages are extracted from
            HTML. LinkedIn isn&apos;t fetched (its terms forbid scraping), so paste the text instead. If both are given, the
            pasted text is used.
          </p>
        </div>
        <ErrorBox message={error} />
        <button className="btn-primary" disabled={busy || (!url.trim() && !text.trim())}>
          {busy && <Spinner className="border-t-white" />} Analyze
        </button>
      </form>
    </>
  );
}
