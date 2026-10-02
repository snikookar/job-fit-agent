"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ErrorBox, PageHeader, StatusChip } from "@/components/ui";
import { api, type ProfileSummary, type RunRow } from "@/lib/api";

export default function Dashboard() {
  const [profile, setProfile] = useState<ProfileSummary | null>(null);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.profile(), api.jobs()])
      .then(([p, r]) => {
        setProfile(p);
        setRuns(r);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const noProfile = profile !== null && profile.total_chunks === 0;

  return (
    <>
      <PageHeader
        title="Resume-to-job fit"
        subtitle="A resume tailoring tool that won't let you lie: every claim is linked to its evidence."
        actions={
          <Link href="/jobs/new" className="btn-primary">
            Analyze a job
          </Link>
        }
      />
      <ErrorBox message={error} />

      {noProfile && (
        <div className="card mb-6 border-amber-200 bg-amber-50">
          <h2 className="font-medium">Start with your profile</h2>
          <p className="mt-1 text-sm text-slate-600">
            Upload your resume and projects, or load the fictional demo profile to try things out.
          </p>
          <Link href="/profile" className="btn-secondary mt-3">
            Set up profile
          </Link>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        {[
          ["1. Profile", "Resume, project write-ups and GitHub READMEs become small, citable chunks."],
          ["2. Match", "Each requirement is matched to evidence. The score is plain arithmetic you can inspect."],
          ["3. Draft + fact-check", "Every sentence cites evidence. A separate judge removes anything unsupported."],
        ].map(([t, d]) => (
          <div key={t} className="card">
            <h3 className="font-medium">{t}</h3>
            <p className="mt-1 text-sm text-slate-600">{d}</p>
          </div>
        ))}
      </div>

      <h2 className="mb-3 mt-10 text-lg font-semibold">Recent analyses</h2>
      {runs.length === 0 ? (
        <p className="text-sm text-slate-500">No analyses yet.</p>
      ) : (
        <div className="card divide-y divide-slate-100 p-0">
          {runs.map((r) => (
            <Link
              key={r.run_id}
              href={`/jobs/${r.run_id}`}
              className="flex flex-wrap items-center gap-3 px-5 py-3 hover:bg-slate-50"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{r.title ?? "Untitled posting"}</div>
                <div className="truncate text-xs text-slate-500">
                  {r.company ?? "Unknown company"} · {r.created_at ? new Date(r.created_at).toLocaleString() : ""}
                </div>
              </div>
              {r.score !== null && <span className="text-sm tabular-nums text-slate-700">{Math.round(r.score)} / 100</span>}
              <StatusChip status={r.status} />
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
