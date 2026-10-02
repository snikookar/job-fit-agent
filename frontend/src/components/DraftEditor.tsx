"use client";

import { useMemo, useState } from "react";
import { api, type Chunk, type Draft, type DraftSentence, type JobState, type Section, type Verdict } from "@/lib/api";
import { wordDiff } from "@/lib/diff";
import { ErrorBox, Spinner } from "./ui";

const SECTION_TITLE: Record<Section, string> = { bullets: "Tailored resume bullets", cover_letter: "Cover letter" };

function sameIds(a: string[], b: string[]) {
  return a.length === b.length && a.every((x, i) => x === b[i]);
}

function findVerdict(verdicts: Verdict[], section: Section, s: DraftSentence): Verdict | undefined {
  return verdicts.find((v) => v.section === section && v.text === s.text && sameIds(v.evidence_ids, s.evidence_ids));
}

function Diff({ before, after }: { before: string; after: string }) {
  return (
    <p className="text-sm leading-relaxed">
      {wordDiff(before, after).map((p, i) =>
        p.kind === "same" ? (
          <span key={i}>{p.text}</span>
        ) : p.kind === "added" ? (
          <ins key={i} className="bg-emerald-100 no-underline">{p.text}</ins>
        ) : (
          <del key={i} className="bg-rose-100 text-rose-700">{p.text}</del>
        ),
      )}
    </p>
  );
}

function SentenceRow({
  section,
  sentence,
  verdict,
  original,
  showDiff,
  readOnly,
  chunks,
  onChange,
  onDelete,
  onOpenEvidence,
}: {
  section: Section;
  sentence: DraftSentence;
  verdict?: Verdict;
  original?: string;
  showDiff: boolean;
  readOnly: boolean;
  chunks: Record<string, Chunk>;
  onChange: (text: string) => void;
  onDelete: () => void;
  onOpenEvidence: (id: string) => void;
}) {
  const unsupported = verdict && !verdict.supported;
  return (
    <li className={`rounded-lg border p-3 ${unsupported ? "border-rose-300 bg-rose-50" : "border-slate-200 bg-white"}`}>
      <div className="flex items-start gap-3">
        <span
          className="mt-1.5 grid h-5 w-5 shrink-0 place-items-center text-sm"
          title={verdict ? `${verdict.supported ? "supported" : "unsupported"} · P(supported) = ${verdict.p_supported}` : "not checked yet"}
        >
          {!verdict ? <span className="h-2 w-2 rounded-full bg-slate-300" /> : verdict.supported ? <span className="text-emerald-600">✓</span> : <span className="text-rose-600">✕</span>}
        </span>
        <div className="min-w-0 flex-1">
          {readOnly ? (
            <p className="text-sm leading-relaxed">{sentence.text}</p>
          ) : (
            <textarea
              className="w-full resize-y rounded-md border border-transparent bg-transparent px-1 py-0.5 text-sm leading-relaxed outline-none hover:border-slate-200 focus:border-slate-400 focus:bg-white"
              rows={Math.max(1, Math.ceil(sentence.text.length / 95))}
              value={sentence.text}
              onChange={(e) => onChange(e.target.value)}
              aria-label={`${SECTION_TITLE[section]} sentence`}
            />
          )}
          {showDiff && original && (
            <div className="mt-2 rounded-md bg-slate-50 p-2">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-slate-400">changes vs. original</div>
              <Diff before={original} after={sentence.text} />
            </div>
          )}
          {unsupported && <p className="mt-1 text-xs text-rose-700">Unsupported: {verdict.reason}</p>}
          <div className="mt-1.5 flex flex-wrap items-center gap-1">
            {sentence.evidence_ids.map((id) =>
              id === "job" ? (
                <span key={id} className="chip bg-sky-50 text-sky-700" title="Statement about the role, backed by the job posting">
                  job posting
                </span>
              ) : (
                <button
                  key={id}
                  onClick={() => onOpenEvidence(id)}
                  className={`chip font-mono hover:underline ${chunks[id] ? "bg-slate-100 text-slate-700" : "bg-rose-100 text-rose-700"}`}
                  title={chunks[id]?.text ?? "unknown evidence id"}
                >
                  {id}
                </button>
              ),
            )}
            {!readOnly && (
              <button className="ml-auto text-xs text-slate-400 hover:text-rose-600" onClick={onDelete}>
                remove
              </button>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

export function DraftEditor({
  runId,
  state,
  chunks,
  readOnly,
  onOpenEvidence,
  onSubmitted,
}: {
  runId: string;
  state: JobState;
  chunks: Record<string, Chunk>;
  readOnly: boolean;
  onOpenEvidence: (chunkId: string) => void;
  onSubmitted: () => void;
}) {
  const initial: Draft = (readOnly ? state.final_draft : state.draft) ?? state.draft ?? { bullets: [], cover_letter: [] };
  const [draft, setDraft] = useState<Draft>(initial);
  const [verdicts, setVerdicts] = useState<Verdict[]>([...(state.verdicts ?? []), ...(state.final_verdicts ?? [])]);
  const [showDiff, setShowDiff] = useState(false);
  const [keepUnsupported, setKeepUnsupported] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const edited = JSON.stringify(draft) !== JSON.stringify(state.draft);
  const status = useMemo(() => {
    let unchecked = 0;
    let unsupported = 0;
    for (const section of ["bullets", "cover_letter"] as Section[]) {
      for (const s of draft[section]) {
        const v = findVerdict(verdicts, section, s);
        if (!v) unchecked++;
        else if (!v.supported) unsupported++;
      }
    }
    return { unchecked, unsupported };
  }, [draft, verdicts]);

  function update(section: Section, index: number, text: string) {
    setDraft((d) => ({ ...d, [section]: d[section].map((s, i) => (i === index ? { ...s, text } : s)) }));
  }
  function remove(section: Section, index: number) {
    setDraft((d) => ({ ...d, [section]: d[section].filter((_, i) => i !== index) }));
  }

  async function check(): Promise<Verdict[] | null> {
    setBusy("check");
    setError(null);
    try {
      const v = await api.check(runId, draft);
      setVerdicts(v);
      return v;
    } catch (e) {
      setError((e as Error).message);
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function submit(approved: boolean) {
    setError(null);
    if (approved && status.unchecked > 0 && !(await check())) return;
    setBusy(approved ? "approve" : "reject");
    try {
      await api.review(runId, {
        approved,
        draft: approved && edited ? draft : undefined,
        keep_unsupported_edits: keepUnsupported,
      });
      onSubmitted();
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  const removed = state.removed ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} />
          Show changes vs. original bullets
        </label>
        <span className="ml-auto text-xs text-slate-500">
          ✓ supported by its evidence · <span className="text-rose-600">✕ unsupported</span> · • edited, not checked yet
        </span>
      </div>

      {(["bullets", "cover_letter"] as Section[]).map((section) => (
        <section key={section}>
          <h3 className="mb-2 font-medium">{SECTION_TITLE[section]}</h3>
          {section === "cover_letter" && (
            <p className="mb-2 text-xs text-slate-500">Greeting and sign-off are added in the exported document.</p>
          )}
          <ol className="space-y-2">
            {draft[section].map((s, i) => (
              <SentenceRow
                key={`${section}-${i}`}
                section={section}
                sentence={s}
                verdict={findVerdict(verdicts, section, s)}
                original={section === "bullets" ? chunks[s.evidence_ids[0]]?.text : undefined}
                showDiff={showDiff}
                readOnly={readOnly}
                chunks={chunks}
                onChange={(t) => update(section, i, t)}
                onDelete={() => remove(section, i)}
                onOpenEvidence={onOpenEvidence}
              />
            ))}
            {draft[section].length === 0 && <li className="text-sm text-slate-400">No sentences.</li>}
          </ol>
        </section>
      ))}

      {removed.length > 0 && (
        <section>
          <h3 className="mb-2 font-medium text-rose-700">Removed by the fact-check ({removed.length})</h3>
          <ul className="space-y-2">
            {removed.map((v, i) => (
              <li key={i} className="rounded-lg border border-rose-200 bg-white p-3 text-sm">
                <p className="text-slate-500 line-through">{v.text}</p>
                <p className="mt-1 text-xs text-rose-700">
                  {v.edited_by_user ? "Your edit: " : ""}
                  {v.reason}
                </p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {!readOnly && (
        <div className="card sticky bottom-4 space-y-3 border-slate-300 shadow-lg">
          <ErrorBox message={error} />
          {status.unsupported > 0 && (
            <label className="flex items-start gap-2 text-sm text-rose-800">
              <input type="checkbox" className="mt-1" checked={keepUnsupported} onChange={(e) => setKeepUnsupported(e.target.checked)} />
              <span>
                {status.unsupported} edited sentence(s) aren&apos;t supported by their evidence. They will be removed on
                approval, unless you keep them on purpose.
              </span>
            </label>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-secondary" disabled={!!busy || status.unchecked === 0} onClick={check}>
              {busy === "check" && <Spinner />} Check edits {status.unchecked > 0 && `(${status.unchecked})`}
            </button>
            <button className="btn-danger" disabled={!!busy} onClick={() => submit(false)}>
              Reject
            </button>
            <button className="btn-primary ml-auto" disabled={!!busy} onClick={() => submit(true)}>
              {busy === "approve" && <Spinner className="border-t-white" />} Approve &amp; export .docx
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
