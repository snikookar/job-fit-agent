# Phase 1: Foundation

**Goal:** a repo you can install with one command, a database that works with or without Docker, the shared data models, and a fictional profile for demos.

## Files created

| File | Purpose |
|---|---|
| `backend/pyproject.toml` | Python dependencies, optional extras (`ml`, `docling`, `browser`, `tracing`) and the ruff/pytest config |
| `backend/.python-version` | Pins Python 3.12 for the backend |
| `backend/jobfit/config.py` | All settings, read from environment variables and `.env` |
| `backend/jobfit/schemas.py` | Pydantic models from the spec (`Requirement`, `JobRequirements`, `Evidence`, `DraftSentence`, `Draft`) plus supporting ones (`Chunk`, `ScoreBreakdown`, `Gap`, `Verdict`, `ReviewDecision`) |
| `backend/jobfit/db/models.py` | SQLAlchemy tables: `chunks`, `profile_info`, `runs`, `applications` |
| `backend/jobfit/db/session.py` | Engine creation, `init_db()` and a `session_scope()` context manager |
| `backend/tests/conftest.py` | Each test gets a fresh SQLite DB, offline LLMs and hash embeddings |
| `sample_profile/` | Mira Lindqvist, a fictional persona: resume (Markdown and generated PDF), projects, README snapshots |
| `sample_profile/build_resume_pdf.py` | Renders `resume.md` to a real PDF, so ingestion tests exercise the PDF parser |
| `docker-compose.yml` | Postgres 17 with pgvector (more services come in phase 10) |
| `.env.example`, `.gitignore` | Config template; secrets and local data stay out of git |
| `docs/SPEC.md` | The original project spec |

## Technology choices

### Package manager: uv
| Option | Verdict |
|---|---|
| **uv** ✅ | Very fast, writes a lockfile (`uv.lock`) for reproducible installs, and can download the right Python version itself. One tool replaces pip + venv + pyenv. |
| pip + requirements.txt | No lockfile by default, so CI and your laptop can drift apart. |
| Poetry | Works well, but is slower and doesn't manage Python versions. |

I pinned **Python 3.12** rather than your installed 3.14. Heavy optional packages (PyTorch, Docling) publish wheels for new Python versions late, and 3.12 matches the Docker image. uv downloads 3.12 automatically.

### Optional extras instead of one big install
`bge-m3` and the reranker need PyTorch (1–2 GB), Docling downloads layout models, and Playwright downloads a browser. If these were required, CI would be slow and a first-time visitor to the repo would wait 10 minutes before seeing anything. So the core install is light, and each heavy piece is an extra:

```bash
uv sync                    # core: runs everything with lightweight fallbacks
uv sync --extra ml         # real bge-m3 embeddings + bge reranker
uv sync --all-extras       # everything
```

### Database: SQLite locally, Postgres + pgvector in Docker
The spec asks for PostgreSQL + pgvector, but your machine has no Docker or Postgres. Rather than force a setup step, the same SQLAlchemy models run on both:

- `EmbeddingType` (in `db/models.py`) stores vectors as a pgvector `vector(1024)` column on Postgres and as a JSON array on SQLite.
- On Postgres, similarity search runs in SQL (`<=>` cosine distance). On SQLite it runs in NumPy. A personal profile has hundreds of chunks, not millions, so this is fast enough.
- You switch with a single variable: `DATABASE_URL`.

| Option | Verdict |
|---|---|
| **SQLAlchemy 2.0 + both DBs** ✅ | Zero-setup local runs, while the "real" stack stays pgvector |
| Postgres only | Matches the spec, but nobody can run it without Docker |
| A dedicated vector DB (Qdrant, Chroma) | One more service to run. pgvector keeps profile, tracker and checkpoints in one database, as the spec intends |

**Migrations:** for now the tables are created with `Base.metadata.create_all()`. Alembic is the right tool once the schema has to evolve under real users' data. For an MVP it adds ceremony without benefit.

### Settings: pydantic-settings
Settings are typed, validated and read from environment variables or `.env`, the same way in Docker, CI and local runs. It's already part of the Pydantic ecosystem the project uses for structured output.

### Fictional profile
The spec requires a fictional persona for the public demo. Mira's profile is deliberately imperfect: she has only a learning repo for Kubernetes. That gives the fabrication eval a realistic trap, e.g. a planted claim like *"5 years of Kubernetes in production"*.

## Run it

```bash
cd backend
uv sync
uv run pytest
```
