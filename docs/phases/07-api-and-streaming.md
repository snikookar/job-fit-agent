# Phase 7: FastAPI + live progress via SSE

**Goal:** an HTTP API for the frontend. Runs execute in the background, and the browser sees each node finish in real time.

```
Browser                         FastAPI                          worker thread
  │ POST /api/jobs {text} ───────► RunManager.start() ─────────────► agent.start() (graph)
  │ ◄──── 202 {run_id}                                                │ node events
  │ GET /api/jobs/{id}/events ───► subscribe() reads the event log ◄──┘ appended with seq
  │ ◄═══ SSE: fetch_job ✓, parse_requirements ✓, ... interrupt ⏸
  │ GET /api/jobs/{id} ──────────► full state from the checkpoint + cited chunks
  │ POST /api/jobs/{id}/check ───► judge_draft() on the user's edits (no resume)
  │ POST /api/jobs/{id}/review ──► RunManager.resume() ─────────────► agent.resume()
  │ GET  /api/jobs/{id}/events?after=N  ═══ SSE: human_review ✓, export ✓, done ■
  │ GET /api/jobs/{id}/docx ─────► the Word file
```

## Files created

| File | Purpose |
|---|---|
| `jobfit/api/main.py` | `create_app()`: lifespan (DB init, agent, run manager), CORS, `/api/health` |
| `jobfit/api/runs.py` | `RunManager`: background threads, per-run event log, status in the `runs` table, SSE subscription |
| `jobfit/api/routes_profile.py` | Upload resume / projects, connect GitHub, sample profile, browse chunks, contact info |
| `jobfit/api/routes_jobs.py` | Start, list, get, stream, check, review, download |
| `jobfit/api/routes_tracker.py` | Kanban CRUD + document download |
| `tests/test_api.py` | Real HTTP flow, including reading the SSE stream |

FastAPI also generates interactive docs at **http://localhost:8000/docs**.

## Technology choices

### FastAPI
| Option | Verdict |
|---|---|
| **FastAPI** ✅ | Uses the same Pydantic models as the graph, so request validation is free (`ReviewDecision`, `Draft`). Auto-generated OpenAPI docs, async support for streaming, and it's the standard for Python AI backends |
| Flask | Simpler, but no built-in validation or async streaming |
| Django | Far more than a single-user tool needs |

### Server-Sent Events instead of WebSockets or polling
| Option | Verdict |
|---|---|
| **SSE** ✅ (`sse-starlette`) | Progress flows one way (server → browser), which is exactly what SSE is for. It's plain HTTP, the browser's `EventSource` reconnects automatically, and it passes through proxies |
| WebSockets | Two-way, which isn't needed here, and needs more code on both sides |
| Polling `GET /jobs/{id}` | Works, but with lag and wasted requests. The UI still uses it once at the end to load the full state |

Each event has a sequence number (`id:`). The client can reconnect with `?after=N` and only gets what it missed, so a page reload or a second tab can catch up. After an approval, the same stream continues from where it paused.

### Background threads + an event log
The graph and the LLM SDK calls are synchronous, so each run executes in a **worker thread**, and FastAPI's event loop stays free. Events go into an in-memory log. The SSE endpoint checks it every 150 ms. Polling a local list is simpler and harder to get wrong than handing events across threads to asyncio queues, and a 150 ms delay is invisible next to LLM calls that take seconds.

What happens if the server restarts?
- The **full state** is in the LangGraph checkpoint, and the **status** is in the `runs` table. A run waiting for review can still be approved after a restart.
- A run that was *in the middle of a node* is marked failed with a clear message (`mark_orphaned_runs`).
- Only the progress log (in memory) is lost, and it's only needed while a run is live.

A job queue (Celery, RQ, Arq) would add Redis and a worker process. That's worth it for many users, but not for a local single-user tool.

### Validating edits before approving
`POST /check` runs the same `judge_draft()` as the graph, without resuming it. The editor can highlight unsupported sentences in red **while the user edits**, before anything is approved. Unchanged supported sentences come from the cache, so a check usually only judges what changed.

### No authentication, on purpose
This is a local tool that holds a resume (spec risk: *"Resume privacy → run locally"*). The README says not to expose it publicly. Adding auth would suggest it's safe to host, which isn't the intended use.
