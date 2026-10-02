"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Health } from "@/lib/api";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/profile", label: "Profile" },
  { href: "/jobs/new", label: "New job" },
  { href: "/tracker", label: "Tracker" },
];

export function Nav() {
  const pathname = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [down, setDown] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setDown(true));
  }, []);

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span className="grid h-7 w-7 place-items-center rounded-md bg-slate-900 text-xs text-white">JF</span>
          job-fit-agent
        </Link>
        <nav className="flex flex-wrap gap-1 text-sm">
          {LINKS.map((l) => {
            const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`rounded-md px-3 py-1.5 ${active ? "bg-slate-100 font-medium text-slate-900" : "text-slate-600 hover:text-slate-900"}`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto text-xs">
          {down && <span className="chip bg-rose-100 text-rose-800">Backend not reachable on :8000</span>}
          {health?.offline_mode && (
            <span
              className="chip bg-amber-100 text-amber-800"
              title="No API keys configured: rule-based heuristics instead of LLMs. Good for trying the UI, not for real applications."
            >
              Offline mode (no LLM keys)
            </span>
          )}
          {health && !health.offline_mode && (
            <span className="chip bg-emerald-100 text-emerald-800" title={`judge: ${health.judge}`}>
              {health.writer.split(":")[1]} · judge {health.judge.split(":")[1]}
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
