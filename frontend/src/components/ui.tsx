"use client";

import type { ReactNode } from "react";
import type { RunStatus } from "@/lib/api";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{message}</div>;
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-800 ${className}`}
      aria-label="loading"
    />
  );
}

const STATUS_STYLE: Record<RunStatus, string> = {
  running: "bg-sky-100 text-sky-800",
  awaiting_review: "bg-amber-100 text-amber-800",
  done: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
};
const STATUS_LABEL: Record<RunStatus, string> = {
  running: "Running",
  awaiting_review: "Needs review",
  done: "Done",
  failed: "Failed",
};

export function StatusChip({ status }: { status: RunStatus }) {
  return <span className={`chip ${STATUS_STYLE[status]}`}>{STATUS_LABEL[status]}</span>;
}

/** 0..100 score as a ring. Color reflects the band, the number is always shown. */
export function ScoreRing({ score, size = 96 }: { score: number; size?: number }) {
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  const color = score >= 70 ? "#059669" : score >= 45 ? "#d97706" : "#e11d48";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`fit score ${score}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth="8" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="8"
        strokeLinecap="round"
        strokeDasharray={`${(c * score) / 100} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" className="fill-slate-900 text-xl font-semibold">
        {Math.round(score)}
      </text>
    </svg>
  );
}

/** Evidence strength as a small bar with the number next to it. */
export function StrengthBar({ value }: { value: number }) {
  const color = value >= 0.5 ? "bg-emerald-500" : value > 0 ? "bg-amber-400" : "bg-slate-300";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
        <div className={`h-full ${color}`} style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <span className="w-8 text-xs tabular-nums text-slate-500">{value.toFixed(2)}</span>
    </div>
  );
}
