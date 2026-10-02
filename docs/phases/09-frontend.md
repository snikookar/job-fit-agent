# Phase 9: Next.js frontend

**Goal:** the five screens from the spec: profile, new job with live progress, match view, draft editor, tracker Kanban.

| Screen | Route | What it does |
|---|---|---|
| Dashboard | `/` | Recent analyses with status and score; prompts you to set up a profile |
| Profile | `/profile` | Upload resume/projects, import GitHub READMEs, load the demo profile, contact details, browse and filter every indexed chunk |
| New job | `/jobs/new` | Paste text or a link |
| Job | `/jobs/[id]` | Live progress (SSE), then tabs: **Match** (requirement → evidence → points), **Gaps**, **Draft & review**, **Posting** |
| Tracker | `/tracker` | Kanban: saved → applied → interview → offer / rejected |

## Files created

| File | Purpose |
|---|---|
| `src/lib/api.ts` | Typed API client; the types mirror `backend/jobfit/schemas.py` |
| `src/lib/diff.ts` | Word-level LCS diff for "original bullet vs tailored bullet" |
| `src/components/ProgressTimeline.tsx` | One row per graph node: ✓ / spinner / ⏸ / ✕, details and timing; shows ×2 when writer and judge loop |
| `src/components/MatchView.tsx` | Score ring, must-have coverage, requirements table with clickable evidence; gaps list |
| `src/components/ChunkDrawer.tsx` | Side panel with the full source chunk and the quote highlighted |
| `src/components/DraftEditor.tsx` | Editable sentences with ✓/✕ per sentence, evidence chips, diff toggle, "Check edits", approve/reject, removed sentences |
| `src/components/ui.tsx`, `Nav.tsx` | Shared bits; the nav shows **Offline mode** when no LLM keys are set |
| `src/app/**/page.tsx` | The pages |

## Technology choices

### Next.js (App Router) + Tailwind, as in the spec
| Option | Verdict |
|---|---|
| **Next.js + Tailwind** ✅ | The spec's choice and the most common stack for portfolio projects. File-based routing gives the five screens for free |
| Vite + React | Lighter, and would work just as well for a client-only app |
| Streamlit / Gradio | Quick for demos, but a diff editor and a drag-and-drop Kanban don't fit them well |

All pages are **client components**: everything is interactive and talks to the local FastAPI backend, so there's nothing to server-render. The browser calls the backend directly (`NEXT_PUBLIC_API_URL`, default `http://localhost:8000`) instead of going through a Next.js proxy, because some proxies buffer SSE streams.

### Few dependencies on purpose
The only runtime dependencies are `next`, `react` and `react-dom`.
- **Diff:** a 40-line word-level LCS (`lib/diff.ts`). Bullets are short, so it's fast, and it saves a package.
- **Kanban:** native HTML5 drag and drop, plus a dropdown on each card as a keyboard and touch alternative. HTML5 DnD doesn't work on touch screens, so the dropdown is necessary. `dnd-kit` would give nicer animations but adds a dependency for one screen.
- **Live progress:** the browser's built-in `EventSource`.
- **Fonts:** a system font stack. `next/font/google` downloads fonts from Google at build time, which failed in a restricted network and makes an outside request this privacy-minded tool doesn't need.

### How the review UI enforces "won't let you lie"
- Every sentence shows **✓ supported / ✕ unsupported / • not checked yet**, with the judge's reason in red.
- Evidence chips open the original chunk. An unknown ID is shown in red.
- An edit marks the sentence as *not checked*. **Check edits** calls `POST /check` (the same three-layer judge), and approving checks any remaining edits automatically.
- Unsupported edits are removed on approval unless you tick *"keep them on purpose"*.
- Sentences removed by the fact-check are listed with their reasons, so nothing disappears silently.

## Tested by hand in the browser
Loaded the demo profile → pasted the Berlin posting → watched the nodes complete live → the run paused for review → added "...ran Kubernetes in production for 5 years" to a bullet → **Check edits** flagged it in red (*number not found in the cited evidence: 5*) → approved → the bullet was removed, the `.docx` was exported and a tracker card appeared → moved the card to *interview*. No console errors.

Not verified: drag and drop with a real mouse. Automated drags in the test browser don't fire HTML5 drag events, so I tested moving cards with the dropdown, which uses the same update call.
