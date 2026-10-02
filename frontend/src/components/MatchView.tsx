"use client";

import type { Chunk, Evidence, Gap, JobState } from "@/lib/api";
import { ScoreRing, StrengthBar } from "./ui";

const ASSESSMENT_STYLE = {
  full: "bg-emerald-100 text-emerald-800",
  partial: "bg-amber-100 text-amber-800",
  none: "bg-slate-100 text-slate-600",
};

export function MatchView({
  state,
  chunks,
  onOpenEvidence,
}: {
  state: JobState;
  chunks: Record<string, Chunk>;
  onOpenEvidence: (chunkId: string, quote?: string) => void;
}) {
  const job = state.requirements;
  const score = state.score;
  if (!job || !score) return null;
  const reqById = new Map(job.requirements.map((r) => [r.id, r]));

  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center gap-6">
        <ScoreRing score={score.score} />
        <div className="min-w-0 flex-1">
          <h2 className="text-xl font-semibold">{job.title}</h2>
          <p className="text-sm text-slate-600">{[job.company, job.location].filter(Boolean).join(" · ") || "—"}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {job.remote !== "unknown" && <span className="chip bg-slate-100 text-slate-700">{job.remote}</span>}
            {job.visa_sponsorship !== "unknown" && (
              <span className="chip bg-slate-100 text-slate-700">visa sponsorship: {job.visa_sponsorship}</span>
            )}
            {state.language && <span className="chip bg-slate-100 text-slate-700">language: {state.language}</span>}
          </div>
        </div>
        <div className="text-sm">
          <div className="text-slate-500">Must-haves covered</div>
          <div className="text-2xl font-semibold tabular-nums">{Math.round(score.must_coverage * 100)}%</div>
        </div>
      </div>

      <div className="card overflow-x-auto p-0">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-3">Requirement</th>
              <th className="px-4 py-3">Strength</th>
              <th className="px-4 py-3">Evidence (click to see the source)</th>
              <th className="px-4 py-3 text-right" title="weight × strength (must = 2, nice = 1)">Points</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {score.items.map((item) => {
              const req = reqById.get(item.requirement_id);
              const evidence: Evidence[] = state.evidence?.[item.requirement_id] ?? [];
              return (
                <tr key={item.requirement_id} className="align-top">
                  <td className="w-[34%] px-4 py-3">
                    <div className="flex items-start gap-2">
                      <span
                        className={`chip shrink-0 ${item.importance === "must" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"}`}
                      >
                        {item.importance}
                      </span>
                      <span>{item.text}</span>
                    </div>
                    {req && <div className="mt-1 pl-12 text-xs text-slate-400">{req.category}{req.years ? ` · ${req.years}+ years` : ""}</div>}
                  </td>
                  <td className="px-4 py-3">
                    <StrengthBar value={item.strength} />
                  </td>
                  <td className="px-4 py-3">
                    {evidence.length === 0 ? (
                      <span className="text-xs text-slate-400">No supporting evidence found</span>
                    ) : (
                      <ul className="space-y-1.5">
                        {evidence.map((e) => (
                          <li key={e.chunk_id}>
                            <button
                              className="group text-left"
                              onClick={() => onOpenEvidence(e.chunk_id, e.quote)}
                              title={chunks[e.chunk_id]?.section}
                            >
                              {e.assessment && (
                                <span className={`chip mr-1.5 ${ASSESSMENT_STYLE[e.assessment]}`}>{e.assessment}</span>
                              )}
                              <span className="text-slate-700 group-hover:underline">
                                {e.quote.length > 140 ? `${e.quote.slice(0, 140)}…` : e.quote}
                              </span>
                              <span className="ml-1.5 font-mono text-[11px] text-slate-400">{e.chunk_id}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                    {item.contribution.toFixed(2)} / {item.weight}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="border-t border-slate-100 px-4 py-3 text-xs text-slate-500">
          Score = 100 × Σ points / Σ weights. Strength = assessment (full / partial / none) adjusted by the reranker score.
          No LLM decides the number.
        </p>
      </div>
    </div>
  );
}

export function GapsView({ gaps }: { gaps: Gap[] }) {
  if (gaps.length === 0) return <div className="card text-sm text-slate-600">No gaps: every requirement has good evidence.</div>;
  return (
    <div className="space-y-3">
      {gaps.map((g) => (
        <div key={g.requirement_id} className="card">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`chip ${g.importance === "must" ? "bg-rose-100 text-rose-800" : "bg-slate-100 text-slate-600"}`}>
              {g.importance}
            </span>
            <span className="font-medium">{g.text}</span>
            <span className="ml-auto text-xs text-slate-500">best evidence {g.best_strength.toFixed(2)}</span>
          </div>
          <p className="mt-2 text-sm text-slate-600">{g.suggestion}</p>
        </div>
      ))}
    </div>
  );
}
