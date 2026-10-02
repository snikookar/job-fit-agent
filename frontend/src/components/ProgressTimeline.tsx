"use client";

import { NODE_LABELS, type RunEvent } from "@/lib/api";
import { Spinner } from "./ui";

const ORDER = Object.keys(NODE_LABELS);

function detail(e: RunEvent): string {
  const d = e.data as Record<string, unknown>;
  if (Object.keys(d).length <= 1) return ""; // only timing info available
  switch (e.node) {
    case "parse_requirements":
      return `${d.requirements} requirements`;
    case "match_evidence":
      return `${d.with_evidence} with evidence`;
    case "score":
      return `score ${d.score}`;
    case "gap_analysis":
      return `${d.gaps} gaps`;
    case "writer":
      return `round ${d.round} · ${d.sentences} sentences`;
    case "grounding_judge":
      return Number(d.unsupported) ? `${d.unsupported} unsupported` : Number(d.removed) ? `${d.removed} removed` : "all supported";
    case "export":
      return d.docx ? "document ready" : "logged";
    default:
      return "";
  }
}

/** One row per graph node. Writer and judge can run twice (revision loop); the latest run is shown. */
export function ProgressTimeline({ events, active }: { events: RunEvent[]; active: boolean }) {
  const latest = new Map<string, RunEvent>();
  const runs = new Map<string, number>();
  for (const e of events) {
    if (e.type === "node" && e.node) {
      latest.set(e.node, e);
      runs.set(e.node, (runs.get(e.node) ?? 0) + 1);
    }
  }
  const last = events[events.length - 1];
  const paused = last?.type === "interrupt";
  const failed = last?.type === "error" ? last : null;
  const firstPending = ORDER.find((n) => !latest.has(n));

  return (
    <ol className="space-y-1">
      {ORDER.map((node) => {
        const e = latest.get(node);
        const isFailed = failed && (failed.node === node || (!failed.node && node === firstPending));
        const isCurrent = !e && !isFailed && node === firstPending && (active || (paused && node === "human_review"));
        const seconds = (e?.data.trace as { seconds?: number } | undefined)?.seconds;
        return (
          <li key={node} className="flex items-start gap-3 rounded-md px-1 py-1.5 text-sm">
            <span className="grid h-5 w-5 shrink-0 place-items-center">
              {e ? (
                <span className="text-emerald-600">✓</span>
              ) : isFailed ? (
                <span className="text-rose-600">✕</span>
              ) : isCurrent && paused ? (
                <span className="text-amber-600">⏸</span>
              ) : isCurrent ? (
                <Spinner />
              ) : (
                <span className="h-2 w-2 rounded-full bg-slate-300" />
              )}
            </span>
            <span className="min-w-0 flex-1">
              <span className={e || isCurrent ? "text-slate-900" : "text-slate-400"}>
                {NODE_LABELS[node]}
                {(runs.get(node) ?? 0) > 1 && <span className="ml-1 text-xs text-slate-500">×{runs.get(node)}</span>}
              </span>
              {(e || (isCurrent && paused)) && (
                <span className="block text-xs text-slate-500">
                  {e ? detail(e) : "waiting for you"}
                </span>
              )}
            </span>
            {seconds !== undefined && <span className="text-xs tabular-nums text-slate-400">{seconds.toFixed(1)}s</span>}
          </li>
        );
      })}
    </ol>
  );
}
