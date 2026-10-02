# Phase 6: The full graph, human review, .docx export and tracker

**Goal:** wire all nodes into one LangGraph graph that pauses for the user's approval, survives restarts, exports a Word file and logs the application.

```
fetch_job → parse_requirements → match_evidence → score → gap_analysis → writer ⇄ grounding_judge
                                                                                     │
                                         ┌───────── interrupt() ─ waits for the user ┘
                                         ▼
                                   human_review ── approve / edit / reject ──► export ──► END
                                                                                (.docx + tracker)
```

## Files created

| File | Purpose |
|---|---|
| `jobfit/graph/graph.py` | `build_graph()`: nodes, edges and the conditional writer ⇄ judge edge |
| `jobfit/graph/checkpoint.py` | `make_checkpointer()`: `PostgresSaver` or `SqliteSaver` |
| `jobfit/graph/nodes/human_review.py` | `interrupt()`, then re-checks any sentences the user edited |
| `jobfit/graph/nodes/export.py` | .docx + tracker card (a rejected draft gets a card without a document) |
| `jobfit/export/docx.py` | python-docx document: header, tailored bullets, cover letter. English or German greeting/closing. Optional template and evidence comments |
| `jobfit/tracker.py` | CRUD for the Kanban: saved → applied → interview → offer / rejected |
| `jobfit/graph/runner.py` | `JobFitAgent.start() / resume() / state()`: turns the LangGraph stream into simple events (`node`, `interrupt`, `done`, `error`) |
| `jobfit/cli.py` | `uv run jobfit load-sample | ingest | ingest-github | analyze` |
| `tests/test_graph.py` | Full runs, restart during review, edits, rejection, errors, the loop inside the graph, docx |

## Design decisions

### Human-in-the-loop with `interrupt()` + a checkpointer
| Option | Verdict |
|---|---|
| **`interrupt()` inside the node + a persistent checkpointer** ✅ | The node pauses, the full state is saved in the DB, and `Command(resume=decision)` continues exactly there. Works across HTTP requests and server restarts (tested in `test_review_survives_a_restart`) |
| `interrupt_before=["human_review"]` | The older static breakpoint. It works, but the resume value doesn't flow into the node as naturally |
| Split into two graphs (analyze, then export) | You lose the single traceable run, and state has to be stored by hand |

**Checkpointer:** `PostgresSaver` with Docker (one database for profile, tracker and checkpoints, as the spec says), `SqliteSaver` locally. They share the same interface, so the code doesn't change.

One LangGraph detail: on resume, the node runs again **from the top**, so there is nothing expensive before `interrupt()`.

### Edits are fact-checked too
The user is the final authority, but the promise is "won't let you lie", and an edit could add a claim. So sentences the user changed go through the same three-layer `judge_draft()`:
- By default, unsupported edits are **removed** and listed (marked `edited_by_user`).
- With `keep_unsupported_edits=true` the user can keep them on purpose. That's a conscious decision, not an accident.
- The UI (Phase 9) can call a "check" endpoint first, so the user sees red highlights before approving.

### Export: python-docx
| Option | Verdict |
|---|---|
| **python-docx** ✅ | Pure Python, edits real .docx files, supports templates (`EXPORT_TEMPLATE=my_resume.docx` keeps your styles, header and footer) and, since v1.2, comments |
| docxtpl (Jinja in Word) | Good for fixed layouts, but our content is a variable list of sentences |
| PDF (WeasyPrint, ReportLab) | Recruiters and ATSs prefer editable Word files, and the user may want to tweak the text |
| pandoc | An external binary dependency |

`evidence_comments=True` adds a Word comment to each sentence listing its sources, like a reviewer's notes. It's useful for a final check (remove the comments before sending).

### One runner for API, CLI and eval
`JobFitAgent` hides LangGraph's stream format (`{"node": update}`, `"__interrupt__"`) behind four event types. The FastAPI endpoint (Phase 7), the CLI and the eval scripts all use it, so they behave the same way. Node errors (for example a page that blocks bots) become `error` events with the failing node's name, instead of a crash.

## Try it

```bash
cd backend
uv run jobfit load-sample
uv run jobfit analyze --file tests/fixtures/ai_engineer_berlin.md --approve
```
