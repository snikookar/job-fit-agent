# Phase 3: LLM layer, `fetch_job` and `parse_requirements`

**Goal:** get a job posting from a URL or pasted text, and turn it into structured `JobRequirements`.

## Files created

| File | Purpose |
|---|---|
| `jobfit/llm/base.py` | The `LLM` protocol: a single method, `structured(task, system, user, schema, context)`, plus usage tracking |
| `jobfit/llm/api.py` | `OpenAICompatibleLLM`: works with DeepSeek, GLM, OpenAI, vLLM, Ollama... JSON mode + Pydantic validation + one repair retry. Langfuse tracing if configured |
| `jobfit/llm/heuristic.py` | `HeuristicLLM`: offline, rule-based provider, so the app runs without API keys |
| `jobfit/llm/__init__.py` | `get_writer_llm()` / `get_judge_llm()`: picks API or heuristic from settings |
| `jobfit/fetching.py` | URL → text: Greenhouse/Lever/Personio APIs, then trafilatura, then Playwright. Refuses LinkedIn |
| `jobfit/graph/state.py` | `JobFitState`: the shared state of the LangGraph graph (all phases) |
| `jobfit/graph/services.py` | `Services`: writer LLM, judge LLM, settings, retriever factory. Tests inject fakes here |
| `jobfit/graph/prompts/` | Prompt templates as Markdown files, plus a tiny loader |
| `jobfit/graph/nodes/_common.py` | `@traced`: records seconds, LLM calls and tokens per node run |
| `jobfit/graph/nodes/fetch_job.py` | Node 1 |
| `jobfit/graph/nodes/parse_requirements.py` | Node 2, plus `normalize()` (dedupe, cap at 30, renumber `r1..rn`) |
| `tests/fakes.py` | `ScriptedLLM`: canned answers per task, for testing graph logic |
| `tests/fixtures/ai_engineer_berlin.md` | A realistic (fictional) job posting |

## Technology choices

### Calling LLMs: the `openai` SDK against OpenAI-compatible endpoints
DeepSeek and GLM both expose OpenAI-compatible APIs, so one client with a different `base_url` covers both. So do OpenAI, Together, Groq, vLLM and Ollama (local models).

| Option | Verdict |
|---|---|
| **openai SDK + base_url** ✅ | One small dependency, any provider, full control over the request |
| LangChain chat models | LangGraph doesn't need LangChain. It would add a large dependency tree and another abstraction layer to debug |
| LiteLLM | Good for 100+ providers, but we only need OpenAI-compatible ones |

### Structured output: JSON mode + Pydantic + one repair retry
| Option | Verdict |
|---|---|
| **JSON mode + Pydantic validation + repair** ✅ | Works on every OpenAI-compatible provider. The JSON Schema goes into the system prompt. If validation fails, the error is sent back once to be fixed |
| Strict `json_schema` response format | Guarantees valid output, but not every provider supports it (DeepSeek and GLM offer JSON mode) |
| Tool/function calling | Works too, but it's a roundabout way to get a single object |
| `instructor` library | Does the same thing as ~40 lines here, as another dependency |

### Two different models: writer ≠ judge
The spec requires the judge to use a *different model* than the writer, so they don't share the same failure modes. The defaults are **DeepSeek** for the writer and **GLM** for the judge. The judge also runs at temperature 0. If you only configure one key, the judge falls back to the writer's model with a warning.

### The offline `HeuristicLLM`
Every node asks for a structured result *by task name* and passes the raw inputs in `context`. That makes a rule-based provider possible: it reads section headings ("What you bring", "Nice to have", "Dein Profil"...), bullets and keywords. That has three benefits:

1. Someone visiting your GitHub repo can run the full app **without API keys**.
2. Tests are deterministic and free.
3. It's an honest baseline: the eval can compare it against the real LLM.

It's intentionally simple, and the README says so.

### Fetching: APIs first, then extraction, then a browser
| Step | Why |
|---|---|
| **Greenhouse / Lever / Personio APIs** | These ATSs publish job data through public endpoints (JSON for Greenhouse/Lever, an XML feed for Personio). Structured fields, no HTML guessing, and it's the intended way to read them |
| **httpx + trafilatura** | trafilatura is one of the best main-content extractors: it strips navigation, cookie banners and footers, and outputs Markdown that keeps the lists |
| **Own HTML→text fallback** | trafilatura can drop content on very small pages, so there's a simple fallback converter |
| **Playwright** (optional extra) | Only when a page is rendered by JavaScript and the steps above got almost nothing. A headless browser is slow and heavy, so it's the last resort |
| **LinkedIn refused** | Scraping violates LinkedIn's terms (out of scope in the spec). The user pastes the text |

Pasted text always wins over a URL, because it's the most reliable input (spec risk: "Job sites block scraping").

**Language detection:** `langdetect` is small, pure Python and offline. The detected language goes into the prompt, so a German posting is understood correctly and the cover letter can match its language.

### Prompts as Markdown files
The prompts live in `graph/prompts/*.md` rather than in Python strings. Prompt changes show up as clean diffs and are easy to review during error analysis (Phase 8). Placeholders use `$name` (`string.Template`), so JSON examples with `{}` need no escaping.

### State holds plain dicts
LangGraph checkpoints the state after every node. Plain JSON-like data is the safest thing to serialize, and it can go straight to the frontend. Nodes validate with the Pydantic models when they read.
