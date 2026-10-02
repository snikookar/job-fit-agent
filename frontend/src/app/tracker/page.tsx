"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorBox, PageHeader } from "@/components/ui";
import { api, type Application } from "@/lib/api";

const COLUMN_STYLE: Record<string, string> = {
  saved: "border-t-slate-400",
  applied: "border-t-sky-500",
  interview: "border-t-violet-500",
  offer: "border-t-emerald-500",
  rejected: "border-t-rose-400",
};

export default function TrackerPage() {
  const [statuses, setStatuses] = useState<string[]>([]);
  const [apps, setApps] = useState<Application[]>([]);
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");

  const refresh = useCallback(async () => {
    const t = await api.tracker();
    setStatuses(t.statuses);
    setApps(t.applications);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .tracker()
      .then((t) => {
        if (cancelled) return;
        setStatuses(t.statuses);
        setApps(t.applications);
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  async function move(id: number, status: string) {
    const before = apps;
    setApps((a) => a.map((x) => (x.id === id ? { ...x, status } : x))); // optimistic
    try {
      await api.updateApplication(id, { status });
    } catch (e) {
      setApps(before);
      setError((e as Error).message);
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    try {
      await api.addApplication({ title: title.trim(), company: company.trim() || undefined });
      setTitle("");
      setCompany("");
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <PageHeader title="Application tracker" subtitle="Drag cards between columns. Approved analyses are added automatically." />
      <ErrorBox message={error} />

      <form onSubmit={add} className="mb-6 flex flex-wrap gap-2">
        <input className="input max-w-xs" placeholder="Job title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <input className="input max-w-xs" placeholder="Company" value={company} onChange={(e) => setCompany(e.target.value)} />
        <button className="btn-secondary" disabled={!title.trim()}>
          Add manually
        </button>
      </form>

      <div className="grid gap-3 overflow-x-auto pb-4 md:grid-cols-5">
        {statuses.map((status) => {
          const cards = apps.filter((a) => a.status === status);
          return (
            <section
              key={status}
              onDragOver={(e) => {
                e.preventDefault();
                setOver(status);
              }}
              onDragLeave={() => setOver(null)}
              onDrop={() => {
                if (dragging !== null) move(dragging, status);
                setDragging(null);
                setOver(null);
              }}
              className={`min-h-64 min-w-44 rounded-xl border-t-4 bg-slate-100/70 p-3 transition ${COLUMN_STYLE[status] ?? ""} ${over === status ? "ring-2 ring-slate-300" : ""}`}
            >
              <h2 className="mb-3 flex items-center justify-between text-sm font-medium capitalize">
                {status}
                <span className="chip bg-white text-slate-500">{cards.length}</span>
              </h2>
              <div className="space-y-2">
                {cards.map((a) => (
                  <article
                    key={a.id}
                    draggable
                    onDragStart={() => setDragging(a.id)}
                    onDragEnd={() => setDragging(null)}
                    className={`cursor-grab rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-sm active:cursor-grabbing ${dragging === a.id ? "opacity-50" : ""}`}
                  >
                    <div className="font-medium leading-snug">{a.title}</div>
                    <div className="text-xs text-slate-500">{a.company ?? "—"}</div>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                      {a.score !== null && <span className="chip bg-slate-100 text-slate-700">fit {Math.round(a.score)}</span>}
                      {a.run_thread_id && (
                        <Link href={`/jobs/${a.run_thread_id}`} className="text-slate-500 underline">
                          analysis
                        </Link>
                      )}
                      {a.has_docx && (
                        <a href={api.applicationDocxUrl(a.id)} className="text-slate-500 underline">
                          .docx
                        </a>
                      )}
                    </div>
                    {/* Keyboard / touch alternative to drag and drop */}
                    <select
                      aria-label="Move to column"
                      className="mt-2 w-full rounded border border-slate-200 bg-white px-1 py-0.5 text-xs text-slate-600"
                      value={a.status}
                      onChange={(e) => move(a.id, e.target.value)}
                    >
                      {statuses.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </div>
    </>
  );
}
