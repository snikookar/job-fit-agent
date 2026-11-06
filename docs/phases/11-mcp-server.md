# Phase 11: MCP server

**Goal:** let an MCP client (Claude Code, Claude Desktop, any agent that speaks the Model Context Protocol) use the agent's capabilities as tools, with the same code paths, the same fact-check and no new way to change the user's data.

```
Claude Code / Desktop ──stdio (JSON-RPC)──► jobfit-mcp (MCPServer)
                                               │ search_profile     → HybridRetriever.search()
                                               │ score_job          → fetch_job → parse_requirements
                                               │                      → match_evidence → score → gap_analysis
                                               │ check_claim        → grounding.judge_draft()
                                               │ list_tracker_cards → tracker.list_applications()
                                               ▼
                                     same database as the web app (SQLite or Postgres + pgvector)
```

## Files created

| File | Purpose |
|---|---|
| `jobfit/mcp_server.py` | `create_server(svc)` registers four tools on the SDK's `MCPServer`; `main()` runs it over stdio |
| `pyproject.toml` | `mcp>=2.3,<3` dependency and the `jobfit-mcp` entry point |
| `tests/test_mcp_server.py` | 12 tests through a real MCP client: tool listing, each tool, bad inputs, and the stdio entry point as a subprocess |

## The tools

| Tool | Reuses | Calls an LLM? | Output schema |
|---|---|---|---|
| `search_profile(query, k)` | `HybridRetriever` (BM25 + dense + RRF + rerank) | no | `Chunk` + reranker score |
| `score_job(job_text)` | the graph's first five nodes, unchanged | yes (writer) | `JobRequirements`, `ScoreBreakdown`, `Evidence`, `Gap` |
| `check_claim(sentence, evidence_ids, section, job_text)` | `judge_draft()`, the three-layer fact-check | only if the cheap checks pass (judge) | `Verdict` |
| `list_tracker_cards(status)` | `tracker.list_applications()` | no | tracker cards |

Every output is an existing Pydantic schema, so MCP clients get the same JSON the API returns, and the SDK publishes an output schema for each tool.

## Technology choices

### The official Python SDK, v2
| Option | Verdict |
|---|---|
| **`mcp` 2.x (`MCPServer`)** ✅ | The reference SDK. Tool input schemas are generated from type hints, so `Annotated[str, Field(max_length=500)]` is both the documentation the model reads and the validation the server runs. Sync tools run in a worker thread, so a slow LLM call doesn't block the protocol loop |
| `mcp` 1.x (`FastMCP`) | Same idea, but v2 is the current major version. v2 renamed `FastMCP` to `MCPServer`; the code uses the v2 names |
| Standalone `fastmcp` | A separate project with more features (proxies, auth helpers) that a local stdio server doesn't need |
| Hand-written JSON-RPC | Possible, but it would duplicate the protocol handling the SDK already tests |

### stdio, not HTTP
The server runs as a child process of the client and talks over stdin/stdout. It opens no port, so the "don't expose it on a network" rule from the [privacy section](../../README.md#-privacy) holds without adding authentication. The SDK also supports Streamable HTTP, which would need auth before it could be offered.

### A server factory, like the API
`create_server(svc)` takes the same `Services` bundle as `create_app(svc)`. Tests pass the offline LLMs or a scripted judge, and the production entry point uses `Services.default()`. The tools are thin wrappers. The module is about 200 lines, mostly tool descriptions and input limits, and none of it is a second copy of retrieval, scoring or grounding logic.

## Design decisions

### Read-only on purpose
All four tools carry `readOnlyHint: true`, and the test suite checks that `score_job` creates no tracker card. Ingesting a resume, approving a draft or moving a card stays in the web app, where a person does it. Two reasons:
- An MCP client may act on instructions it read in a web page or a job posting. A read-only server limits what a prompt injection can do through these tools to *reading* the user's own profile, which the client could already see.
- Write tools would need the human review step the graph has (`interrupt()`). MCP has elicitation for that, but clients support it unevenly, so I left writes out instead of shipping a half-safe version.

`score_job` and `check_claim` are marked `openWorldHint: true` because, outside offline mode, they send the posting and profile text to the configured LLM APIs.

### Tool inputs are untrusted
| Risk | What the server does |
|---|---|
| A model passes a URL from a hostile page | No tool takes a URL. `score_job` takes text, so the server never makes a request it was told to make (no SSRF). The client can fetch the page itself and paste it |
| Huge inputs (cost, memory) | Every string and list has a limit in the input schema: query 500 chars, sentence 1,000, job text 20,000 (the graph's own cap), at most 10 evidence ids of 200 chars each. The SDK rejects anything bigger before the tool runs |
| Invalid values | Enums (`section`, tracker `status`) and ranges (`k` 1–10) are in the schema. The sentence is built as a `DraftSentence`, the same model the writer's output goes through |
| Error messages that leak internals | Expected failures (empty profile, posting too short, `"job"` cited without the posting) raise `ToolError` with a plain message. For anything else the SDK returns only "Error executing tool …"; the traceback goes to the server's stderr log, not to the model |
| A posting that tries to steer the LLM | Not solved by the server. The posting reaches the writer model as it does in the web app, and the output is still forced through the Pydantic schemas and the deterministic score. An injected posting can skew its own score; it can't change stored data through these tools |

### stdout belongs to the protocol
Over stdio, any stray `print()` corrupts the JSON-RPC stream. `main()` sends logging (including the "offline mode" warnings) to stderr, and one test starts the real entry point as a subprocess and lists its tools, which fails if anything else writes to stdout.

### Same database as the web app
The server reads the same `DATABASE_URL` (and `.env`) as the API, so the profile you build in the browser is the one the tools search. Retrieval takes a fresh snapshot per call, so new uploads are visible without restarting the server.

## Testing

All tool tests go through a real MCP `Client` connected to the server in-process, so they cover argument validation, structured output and error results, not just the Python functions. They run in both existing CI jobs (SQLite and Postgres + pgvector) with no new CI configuration.

| Test | What it proves |
|---|---|
| Tool listing | Exactly four tools, all read-only, length limits in the schemas, no URL arguments |
| `search_profile` | The Terraform query returns the resume chunk; blank, oversized and out-of-range inputs are errors |
| `score_job` | Returns the **same** score and gaps as running the graph's nodes directly, and saves nothing |
| `check_claim` | A planted number fails the numbers layer, an unknown id fails the citations layer, and only the sentence that passed both reached the judge |
| `list_tracker_cards` | Status filter works; an unknown status is rejected by the schema |
| stdio subprocess | `python -m jobfit.mcp_server` starts and lists its tools over the real transport |

## Limitations

- Only stdio. A hosted, multi-user version would need Streamable HTTP plus authentication.
- `score_job` runs the full analysis in one call, which takes as long as the web app's first steps (several LLM calls with real models). It doesn't report progress yet; the SDK supports progress notifications, so that's the next step.
- No write tools (ingest, approve, move a card), as explained above.
- Verified with the SDK's own client in CI, and locally with Claude Code (`claude mcp add` as in the README, then `claude mcp list` shows it connected). For Claude Desktop I ran the README's exact `command` and `args` through an MCP stdio client and listed the tools, but haven't tested it inside the Desktop app itself.
