# Phase 2: Profile ingestion and retrieval

**Goal:** turn a resume PDF, project write-ups and GitHub READMEs into small, citable chunks, then find the best evidence for any requirement.

```
resume.pdf ──PyMuPDF──► Markdown ──chunk_resume──►  one chunk per bullet  ─┐
projects/*.md ─────────────────────chunk_sections─► one chunk per section ─┼─► embed ─► chunks table
GitHub READMEs ──REST API──────────chunk_sections─► one chunk per section ─┘

query ─► BM25 ranking ─┐
      └► dense ranking ┴─► RRF fusion (top 20) ─► cross-encoder rerank ─► top 3 evidence
```

## Files created

| File | Purpose |
|---|---|
| `jobfit/profile/parsers.py` | PDF/DOCX/MD → Markdown. Rebuilds headings and bullets in the PDF from font size, bold flags and bullet characters |
| `jobfit/profile/chunking.py` | `chunk_resume` (one chunk per bullet, with role and date range) and `chunk_sections` (one chunk per README section). Drops code blocks and badges |
| `jobfit/profile/tech_tags.py` | ~100 technologies with aliases (`k8s` → Kubernetes) for the `tech_tags` metadata |
| `jobfit/profile/github.py` | Lists a user's repos and downloads their READMEs via the GitHub REST API |
| `jobfit/profile/ingest.py` | Entry points: `ingest_resume`, `ingest_markdown`, `ingest_github`, `load_sample_profile` |
| `jobfit/retrieval/embeddings.py` | `BgeM3Embedder` (real) and `HashEmbedder` (offline fallback) |
| `jobfit/retrieval/rerank.py` | `BgeReranker` (cross-encoder) and `LexicalReranker` (fallback) |
| `jobfit/retrieval/store.py` | Saves chunks with their vectors. Dense search runs in SQL with pgvector, or in NumPy on SQLite |
| `jobfit/retrieval/search.py` | `HybridRetriever`: BM25 + dense → RRF → rerank |
| `jobfit/textutil.py` | Tokenizer, stopwords, tiny stemmer, number extraction (also used by the judge later) |
| `tests/test_profile.py`, `tests/test_retrieval.py` | Parser, chunker, tags, ingestion and search tests |

## Technology choices

### Resume parsing: PyMuPDF by default, Docling optional
| Option | Verdict |
|---|---|
| **PyMuPDF** ✅ (default) | Millisecond parsing, no model downloads, and it exposes font size, bold flags and positions. That's enough to rebuild headings and bullets for typical single-column resumes |
| Docling (`RESUME_PARSER=docling`) | A layout model that handles multi-column and table-heavy resumes much better, but it downloads models and takes seconds per page. Available as an extra |
| pypdf / pdfminer | Plain text only, no font info, so section structure is lost |

Both produce **Markdown**, so there is only one chunker to maintain and test. One detail mattered: PDFs often store ligatures (`ﬂ` instead of `fl`), so the text is NFKC-normalized. Without that, "workflows" wouldn't match a keyword search.

### Chunking: one claim per chunk
The spec says one chunk per resume bullet and one per README section. That fits this project well: the writer cites chunk IDs, and the judge checks a sentence against exactly those chunks. Fixed-size chunking (every 500 tokens) would mix several claims, so a citation would be vague. Chunk IDs are short and readable (`resume:007`, `project:support-copilot:002`), because the LLM has to copy them back correctly.

### Embeddings: bge-m3
| Option | Verdict |
|---|---|
| **bge-m3** ✅ | Open source and runs locally, so the resume never leaves your machine (the spec's privacy risk). Multilingual, which matters for German postings against an English resume. 8k context, 1024 dimensions |
| OpenAI / Voyage embedding APIs | Good quality, but they send your resume to another provider and cost money per call |
| all-MiniLM-L6 | Tiny and fast, but English-only and noticeably weaker |

**Fallback:** `HashEmbedder` hashes words and word pairs into 1024 dimensions. It only measures word overlap, but it needs no download, so tests and CI run in seconds. `EMBEDDING_BACKEND=auto` picks bge-m3 when `uv sync --extra ml` was run.

### Hybrid search + RRF + reranker
- **BM25** (`rank-bm25`) finds exact terms like "Terraform" and "pgvector", where embeddings are surprisingly unreliable.
- **Dense search** finds paraphrases: "shipped LLM features" vs "built a RAG assistant".
- **Reciprocal Rank Fusion** combines both rankings using only ranks, so there's no need to calibrate BM25 scores against cosine similarities.
- **bge-reranker-v2-m3** (a cross-encoder) reads the requirement and the chunk *together*, so it is far more precise than comparing two separate vectors. It only runs on the top 20, which keeps it fast.

Why BM25 in Python rather than Postgres full-text search? A profile has tens to hundreds of chunks, so building a BM25 index in memory takes milliseconds. It also behaves the same on SQLite and Postgres, and Postgres `tsvector` has no BM25 ranking out of the box.

### GitHub: REST API via httpx
The spec mentions the `gh` CLI or cloning. The REST API needs neither a CLI install nor disk space. Two endpoints are enough (`/users/{u}/repos`, `/repos/{r}/readme`), and an optional `GITHUB_TOKEN` raises the rate limit.

## An important observation

With the sample profile, the query *"Kubernetes in production"* returns this as the top hit:

> "Learning project. I have **not** run Kubernetes in production."

The lexical score for it is perfect. **Retrieval similarity is not evidence.** That's why Phase 4 adds an LLM assessment to evidence strength, and Phase 5 adds the grounding judge.
