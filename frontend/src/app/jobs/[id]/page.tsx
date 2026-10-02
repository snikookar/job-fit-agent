"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChunkDrawer } from "@/components/ChunkDrawer";
import { DraftEditor } from "@/components/DraftEditor";
import { GapsView, MatchView } from "@/components/MatchView";
import { ProgressTimeline } from "@/components/ProgressTimeline";
import { ErrorBox, PageHeader, Spinner, StatusChip } from "@/components/ui";
import { api, type JobResponse, type RunEvent } from "@/lib/api";

type Tab = "match" | "gaps" | "draft" | "posting";

/** Rebuild timeline events from the saved trace (authoritative once nothing is running). */
function eventsFromState(data: JobResponse): RunEvent[] {
  const s = data.state;
  const summary = (node: string): Record<string, unknown> => {
    switch (node) {
      case "parse_requirements":
        return { requirements: s.requirements?.requirements.length ?? 0 };
      case "match_evidence":
        return { with_evidence: Object.values(s.evidence ?? {}).filter((e) => e.length).length };
      case "score":
        return { score: s.score?.score };
      case "gap_analysis":
        return { gaps: s.gaps?.length ?? 0 };
      case "writer":
        return { round: s.revision, sentences: (s.draft?.bullets.length ?? 0) + (s.draft?.cover_letter.length ?? 0) };
      case "grounding_judge":
        return { unsupported: 0, removed: (s.removed ?? []).filter((v) => !v.edited_by_user).length };
      case "export":
        return { docx: !!s.docx_path };
      default:
        return {};
    }
  };
  const out: RunEvent[] = (s.trace ?? []).map((t, i) => ({
    type: "node",
    node: t.node,
    data: { trace: t, ...summary(t.node) },
    seq: -1000 + i,
  }));
  if (data.run.status === "awaiting_review") out.push({ type: "interrupt", node: "human_review", data: {}, seq: -1 });
  if (data.run.status === "failed") out.push({ type: "error", node: null, data: { message: data.run.error }, seq: -1 });
  return out;
}

export default function JobPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<JobResponse | null>(null);
  const [live, setLive] = useState<RunEvent[]>([]);
  const [streaming, setStreaming] = useState(0); // bump to (re)connect the event stream
  const [tab, setTab] = useState<Tab | null>(null);
  const [drawer, setDrawer] = useState<{ id: string; quote?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const lastSeq = useRef(-1);

  const load = useCallback(async () => {
    const d = await api.job(id);
    setData(d);
    return d;
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    api
      .job(id)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        if (d.active) setStreaming((k) => k + 1);
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Server-Sent Events: one event per finished node, until the run pauses, ends or fails.
  useEffect(() => {
    if (!streaming) return;
    const es = new EventSource(api.eventsUrl(id, lastSeq.current));
    const onEvent = (ev: Event) => {
      if (!(ev instanceof MessageEvent) || !ev.data) return; // plain connection errors
      const e = JSON.parse(ev.data) as RunEvent;
      if (e.seq <= lastSeq.current) return;
      lastSeq.current = e.seq;
      setLive((prev) => [...prev, e]);
      if (e.type !== "node" || e.node === "score") load().catch(() => {});
    };
    for (const t of ["node", "interrupt", "done", "error"]) es.addEventListener(t, onEvent);
    es.addEventListener("end", () => {
      es.close();
      load().catch(() => {});
    });
    return () => es.close();
  }, [streaming, id, load]);

  const timelineEvents = useMemo(() => {
    if (!data) return [];
    const saved = eventsFromState(data);
    if (!data.active) return saved;
    if (live.some((e) => e.node === "fetch_job")) return live;
    // Resumed run: earlier nodes come from the saved trace, new ones from the stream.
    const liveNodes = new Set(live.map((e) => e.node));
    return [...saved.filter((e) => e.type === "node" && !liveNodes.has(e.node)), ...live];
  }, [data, live]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Spinner />;

  const { run, state, chunks } = data;
  const awaiting = run.status === "awaiting_review" && !data.active;
  const done = run.status === "done";
  const hasResults = !!state.score;
  const currentTab: Tab = tab ?? (awaiting || done ? "draft" : "match");

  return (
    <>
      <PageHeader
        title={state.requirements?.title ?? run.title ?? "Analyzing posting…"}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusChip status={run.status} />
            {state.requirements?.company && <span>{state.requirements.company}</span>}
            {run.job_url && (
              <a href={run.job_url} target="_blank" rel="noreferrer" className="truncate text-slate-500 underline">
                posting
              </a>
            )}
          </span>
        }
        actions={
          done && state.docx_path ? (
            <>
              <a className="btn-primary" href={api.docxUrl(id)}>
                Download .docx
              </a>
              <Link className="btn-secondary" href="/tracker">
                Tracker
              </Link>
            </>
          ) : undefined
        }
      />

      <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
        <aside className="card h-fit lg:sticky lg:top-6">
          <h2 className="mb-2 text-sm font-medium text-slate-500">Progress</h2>
          <ProgressTimeline events={timelineEvents} active={data.active} />
        </aside>

        <div className="min-w-0 space-y-4">
          {run.status === "failed" && (
            <div className="space-y-3">
              <ErrorBox message={run.error ?? "The run failed."} />
              <Link href="/jobs/new" className="btn-secondary">
                Try again (paste the text)
              </Link>
            </div>
          )}
          {awaiting && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              Your turn: review the draft. Every sentence links to its evidence; edits are fact-checked again.
            </div>
          )}
          {done && state.approved === false && (
            <div className="rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-700">
              You rejected this draft. The job was saved in the tracker without a document.
            </div>
          )}

          {!hasResults && run.status === "running" && (
            <div className="card flex items-center gap-3 text-sm text-slate-600">
              <Spinner /> Working on it — results appear here as soon as the score is ready.
            </div>
          )}

          {hasResults && (
            <>
              <div className="flex gap-1 border-b border-slate-200">
                {(
                  [
                    ["match", "Match"],
                    ["gaps", `Gaps (${state.gaps?.length ?? 0})`],
                    ["draft", done ? "Final draft" : "Draft & review"],
                    ["posting", "Posting"],
                  ] as [Tab, string][]
                ).map(([key, label]) => (
                  <button
                    key={key}
                    onClick={() => setTab(key)}
                    disabled={key === "draft" && !state.draft}
                    className={`-mb-px border-b-2 px-4 py-2 text-sm disabled:text-slate-300 ${currentTab === key ? "border-slate-900 font-medium" : "border-transparent text-slate-500 hover:text-slate-800"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {currentTab === "match" && (
                <MatchView state={state} chunks={chunks} onOpenEvidence={(cid, quote) => setDrawer({ id: cid, quote })} />
              )}
              {currentTab === "gaps" && <GapsView gaps={state.gaps ?? []} />}
              {currentTab === "draft" && state.draft && (
                <DraftEditor
                  key={`${run.status}-${state.revision}`}
                  runId={id}
                  state={state}
                  chunks={chunks}
                  readOnly={!awaiting}
                  onOpenEvidence={(cid) => setDrawer({ id: cid })}
                  onSubmitted={() => {
                    setLive([]);
                    load().then(() => setStreaming((k) => k + 1));
                  }}
                />
              )}
              {currentTab === "posting" && (
                <pre className="card whitespace-pre-wrap font-mono text-xs leading-relaxed">{state.job_text}</pre>
              )}
            </>
          )}
        </div>
      </div>

      <ChunkDrawer chunk={drawer ? chunks[drawer.id] ?? null : null} quote={drawer?.quote} onClose={() => setDrawer(null)} />
    </>
  );
}
