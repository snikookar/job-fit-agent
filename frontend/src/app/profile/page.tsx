"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { api, type Chunk, type ProfileSummary } from "@/lib/api";

const INFO_FIELDS = ["name", "headline", "email", "phone", "location", "links"] as const;

export default function ProfilePage() {
  const [profile, setProfile] = useState<ProfileSummary | null>(null);
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [github, setGithub] = useState("");
  const [info, setInfo] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState("");

  const refresh = useCallback(async () => {
    const [p, c] = await Promise.all([api.profile(), api.chunks()]);
    setProfile(p);
    setChunks(c);
    setInfo(p.info);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.profile(), api.chunks()])
      .then(([p, c]) => {
        if (cancelled) return;
        setProfile(p);
        setChunks(c);
        setInfo(p.info);
      })
      .catch((e: Error) => setError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  async function run(label: string, fn: () => Promise<unknown>, done: string) {
    setBusy(label);
    setError(null);
    setNotice(null);
    try {
      await fn();
      await refresh();
      setNotice(done);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const grouped = useMemo(() => {
    const q = filter.toLowerCase();
    const out = new Map<string, Chunk[]>();
    for (const c of chunks) {
      if (q && !`${c.section} ${c.text} ${c.tech_tags.join(" ")}`.toLowerCase().includes(q)) continue;
      out.set(c.source, [...(out.get(c.source) ?? []), c]);
    }
    return out;
  }, [chunks, filter]);

  return (
    <>
      <PageHeader
        title="Profile"
        subtitle={profile ? `${profile.total_chunks} chunks indexed from ${profile.sources.length} sources` : "Loading…"}
        actions={
          <>
            <button
              className="btn-secondary"
              disabled={!!busy}
              onClick={() => run("sample", api.loadSample, "Loaded the fictional demo profile (Mira Lindqvist).")}
            >
              {busy === "sample" && <Spinner />} Load demo profile
            </button>
            <button
              className="btn-danger"
              disabled={!!busy || !profile?.total_chunks}
              onClick={() => confirm("Delete the whole profile?") && run("delete", api.deleteProfile, "Profile deleted.")}
            >
              Delete all
            </button>
          </>
        }
      />
      <div className="mb-4 space-y-2">
        <ErrorBox message={error} />
        {notice && <div className="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-800">{notice}</div>}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card">
          <h2 className="font-medium">Resume</h2>
          <p className="mb-3 mt-1 text-sm text-slate-500">PDF, DOCX or Markdown. Each bullet becomes one chunk.</p>
          <input
            type="file"
            accept=".pdf,.docx,.md,.txt"
            disabled={!!busy}
            className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-white"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) run("resume", () => api.uploadResume(f), `Indexed ${f.name}.`);
              e.target.value = "";
            }}
          />
          {busy === "resume" && <p className="mt-2 flex items-center gap-2 text-sm text-slate-500"><Spinner /> Parsing and embedding…</p>}
        </div>

        <div className="card">
          <h2 className="font-medium">Project write-ups</h2>
          <p className="mb-3 mt-1 text-sm text-slate-500">Markdown files. Each section becomes one chunk.</p>
          <input
            type="file"
            accept=".md,.markdown,.txt"
            multiple
            disabled={!!busy}
            className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-3 file:py-1.5 file:text-white"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? []);
              if (files.length) run("projects", () => api.uploadProjects(files), `Indexed ${files.length} file(s).`);
              e.target.value = "";
            }}
          />
          {busy === "projects" && <p className="mt-2 flex items-center gap-2 text-sm text-slate-500"><Spinner /> Indexing…</p>}
        </div>

        <div className="card">
          <h2 className="font-medium">GitHub READMEs</h2>
          <p className="mb-3 mt-1 text-sm text-slate-500">A username, or repos like owner/repo, owner/repo2.</p>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (github.trim()) run("github", () => api.connectGitHub(github.trim()), "Imported README files.");
            }}
          >
            <input className="input" value={github} onChange={(e) => setGithub(e.target.value)} placeholder="octocat" />
            <button className="btn-primary" disabled={!!busy || !github.trim()}>
              {busy === "github" ? <Spinner className="border-t-white" /> : "Import"}
            </button>
          </form>
        </div>
      </div>

      <div className="card mt-4">
        <h2 className="font-medium">Contact details</h2>
        <p className="mb-3 mt-1 text-sm text-slate-500">Used for the header of the exported Word file.</p>
        <form
          className="grid gap-3 sm:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault();
            run("info", () => api.setInfo(info), "Saved contact details.");
          }}
        >
          {INFO_FIELDS.map((k) => (
            <div key={k}>
              <label className="label capitalize" htmlFor={`info-${k}`}>{k}</label>
              <input
                id={`info-${k}`}
                className="input"
                value={info[k] ?? ""}
                onChange={(e) => setInfo({ ...info, [k]: e.target.value })}
              />
            </div>
          ))}
          <div className="sm:col-span-3">
            <button className="btn-secondary" disabled={!!busy}>Save</button>
          </div>
        </form>
      </div>

      <div className="mb-3 mt-10 flex flex-wrap items-center gap-3">
        <h2 className="text-lg font-semibold">Indexed chunks</h2>
        <input
          className="input ml-auto max-w-xs"
          placeholder="Filter, e.g. Terraform"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>
      {grouped.size === 0 && <p className="text-sm text-slate-500">Nothing indexed yet.</p>}
      <div className="space-y-4">
        {[...grouped.entries()].map(([source, items]) => (
          <details key={source} className="card p-0" open={grouped.size <= 2 || !!filter}>
            <summary className="flex cursor-pointer items-center gap-3 px-5 py-3">
              <span className="font-mono text-sm">{source}</span>
              <span className="chip bg-slate-100 text-slate-600">{items.length}</span>
              <button
                className="ml-auto text-xs text-rose-600 hover:underline"
                onClick={(e) => {
                  e.preventDefault();
                  run("del-" + source, () => api.deleteSource(source), `Removed ${source}.`);
                }}
              >
                remove
              </button>
            </summary>
            <ul className="divide-y divide-slate-100 border-t border-slate-100">
              {items.map((c) => (
                <li key={c.id} className="px-5 py-3 text-sm">
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="font-mono">{c.id}</span>
                    <span>· {c.section}</span>
                    {c.date_range && <span>· {c.date_range}</span>}
                  </div>
                  <p className="whitespace-pre-line">{c.text}</p>
                  {c.tech_tags.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {c.tech_tags.map((t) => (
                        <span key={t} className="chip bg-slate-100 text-slate-600">{t}</span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </>
  );
}
