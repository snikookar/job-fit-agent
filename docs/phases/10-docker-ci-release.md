# Phase 10: Docker, CI and release

**Goal:** anyone can run the project with one command, every push is tested, and the README tells the story.

## Files created

| File | Purpose |
|---|---|
| `backend/Dockerfile` | Python 3.12-slim + uv. Dependencies are installed in their own layer for fast rebuilds. `--build-arg EXTRAS="--extra ml"` adds the bge models |
| `frontend/Dockerfile` | Three stages (deps → build → runtime) using Next.js `standalone` output, so the final image only has the server bundle |
| `docker-compose.yml` | Postgres + pgvector, backend, frontend; health check, volumes for data, exports and downloaded models |
| `.dockerignore`, `frontend/.dockerignore` | Keep `.venv`, `node_modules`, local data and `.env` out of images |
| `.github/workflows/ci.yml` | Five CI jobs (below) |
| `tests/conftest.py` (extended) | `TEST_DATABASE_URL` runs the whole suite against Postgres |
| `README.md`, `LICENSE`, `docs/images/` | The front page of the repo |

## CI jobs

| Job | What it proves |
|---|---|
| **Backend (SQLite)** | ruff lint + format check, 50 tests, no API keys or models needed |
| **Backend (Postgres + pgvector)** | The same 50 tests against a real `pgvector/pgvector:pg17` service: the vector column, `<=>` search in SQL, `PostgresSaver` checkpoints |
| **Eval (offline baseline)** | The eval scripts still run; the results table goes into the job summary, files are uploaded as an artifact |
| **Frontend** | ESLint, TypeScript, production build |
| **Docker images** | `docker compose build` on `main` |

### Verifying Postgres without Docker
Your machine has no Docker. Rather than hope the Postgres path works, I ran the suite locally against a real Postgres + pgvector 0.6.2 using **pgserver** (a pip package bundling portable Postgres binaries): **50/50 passed**. CI repeats this on every push with the official pgvector image.

## Design decisions

### Ports bound to 127.0.0.1
`"127.0.0.1:8000:8000"` instead of `"8000:8000"`. Docker's default publishes on all network interfaces, which would put an app with no login and your resume on your Wi-Fi network.

### Models are optional in the image
The default image is small and starts fast with the lightweight fallbacks. `EXTRAS="--extra ml"` adds PyTorch + sentence-transformers. Models download on first use into the `hf-cache` volume, so they're downloaded only once.

### The API URL is built into the frontend
The browser talks to the backend directly, so `NEXT_PUBLIC_API_URL` must be a URL the *user's browser* can reach (`http://localhost:8000`), not the Docker-internal `http://backend:8000`. That's why it's a build argument.

### Langfuse isn't in the compose file
Self-hosted Langfuse v3 needs ClickHouse, Redis and S3-compatible storage, which is four more containers for an optional feature. Set `LANGFUSE_*` to use Langfuse Cloud or your own deployment, and `uv sync --extra tracing`. Every LLM call is then traced with its task name (`parse_requirements`, `judge`, ...), token counts and cost.

### Formatting enforced
`ruff format --check` fails CI, so the code stays consistent. The whole codebase was formatted once in this phase.

## Publishing to GitHub

```bash
git remote add origin https://github.com/<you>/job-fit-agent.git
git push -u origin main
```

Then replace `YOUR_GITHUB_USERNAME` in the README's CI badge.
