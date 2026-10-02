"use client";

import { useEffect } from "react";
import type { Chunk } from "@/lib/api";

/** Side panel with the full source chunk; the cited quote is highlighted. */
export function ChunkDrawer({ chunk, quote, onClose }: { chunk: Chunk | null; quote?: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!chunk) return null;
  const idx = quote ? chunk.text.indexOf(quote) : -1;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/30" onClick={onClose}>
      <aside
        className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Evidence source"
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-500">Evidence</div>
            <div className="font-mono text-sm">{chunk.id}</div>
          </div>
          <button className="btn-secondary px-2 py-1" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <dl className="mb-4 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-slate-500">Source</dt>
          <dd className="font-mono">{chunk.source}</dd>
          <dt className="text-slate-500">Section</dt>
          <dd>{chunk.section}</dd>
          {chunk.date_range && (
            <>
              <dt className="text-slate-500">Dates</dt>
              <dd>{chunk.date_range}</dd>
            </>
          )}
        </dl>
        <blockquote className="whitespace-pre-line rounded-lg border-l-4 border-slate-300 bg-slate-50 p-4 text-sm leading-relaxed">
          {idx >= 0 && quote ? (
            <>
              {chunk.text.slice(0, idx)}
              <mark className="rounded bg-emerald-100 px-0.5">{quote}</mark>
              {chunk.text.slice(idx + quote.length)}
            </>
          ) : (
            chunk.text
          )}
        </blockquote>
        {chunk.tech_tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1">
            {chunk.tech_tags.map((t) => (
              <span key={t} className="chip bg-slate-100 text-slate-600">{t}</span>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
