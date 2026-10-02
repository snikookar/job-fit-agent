# Phase 4: `match_evidence`, `score` and `gap_analysis`

**Goal:** for every requirement, find evidence in the profile, compute an explainable fit score, and list the gaps.

```
requirement ──hybrid search──► top 3 chunks ──LLM assessment (batched)──► full / partial / none
                                                                       │
              strength = verdict × (0.6 + 0.4 × reranker score) ◄──────┘
                                   │
score = 100 × Σ(weight × best strength) / Σ weight      (must = 2, nice = 1)
gaps  = requirements whose best strength < 0.5  ──LLM──► honest suggestion per gap
```

## Files created

| File | Purpose |
|---|---|
| `jobfit/graph/nodes/match_evidence.py` | Retrieval per requirement + one batched LLM assessment per 10 requirements |
| `jobfit/scoring.py` | Pure functions: `evidence_strength()` and `compute_score()` |
| `jobfit/graph/nodes/score.py` | Thin node around `compute_score` |
| `jobfit/graph/nodes/gap_analysis.py` | Weak requirements → `Gap[]` with suggestions, musts first |
| `jobfit/graph/prompts/assess_evidence.md`, `gap_analysis.md` | Prompts |
| `jobfit/schemas.py` (extended) | `Assessment`, `GapSuggestion`: internal LLM outputs |
| `jobfit/llm/heuristic.py` (extended) | Offline versions: negation detection, years check, gap templates |
| `tests/test_scoring_and_matching.py` | Weight maths, verdict gating, end-to-end nodes, fake-quote protection |

## Design decisions

### Evidence strength: why combine the reranker with an LLM verdict?
Phase 2 showed that retrieval similarity isn't evidence: *"I have **not** run Kubernetes in production"* is a near-perfect match for "Kubernetes in production". So:

- An **LLM verdict** (`full` / `partial` / `none`) decides *whether* a chunk supports the requirement. It sees date ranges, so "3+ years" can be checked.
- The **reranker score** adjusts *how strongly* within that verdict's range.

`strength = value(verdict) × (0.6 + 0.4 × rerank)`, so `none` always gives 0, `full` gives 0.6–1.0, and `partial` gives 0.3–0.5. The verdict acts as a gate and can't be outvoted by a high similarity score.

| Alternative | Why not |
|---|---|
| Reranker score only | Rewards topical similarity, including negations and learning projects |
| LLM score only (0–1 float) | LLMs are poorly calibrated on continuous scores. Three discrete labels are more consistent |
| One LLM call per pair | ~45 calls per job. **Batching** (all pairs of 10 requirements in one call) is about 10× cheaper and faster |

The LLM must also return a **quote**: the exact words in the chunk that support the requirement. If the quote isn't really in the chunk (the LLM paraphrased or invented it), the code falls back to the full chunk text. The UI then never shows a "quote" that doesn't exist.

### Scoring is deterministic code, not an LLM
The spec is explicit about this, and it matters:
- **Reproducible:** the same evidence always gives the same score. An LLM asked "rate this fit 0–100" gives different numbers on each run.
- **Explainable:** each requirement's contribution (`weight × strength`) is shown in the UI, so the user can see why the score is 66 and not 80.
- **Testable:** `tests/test_scoring_and_matching.py` checks the arithmetic exactly.

Musts weigh 2 and nices weigh 1 (from the spec). `must_coverage` (the share of must-haves with strength ≥ 0.5) is reported separately, because a 70% score with one missing must-have is a very different situation from 70% with all musts met.

### Gap suggestions must be honest
The gap prompt says: if you might have this experience, **add it to your profile so it can be cited**; otherwise build it or address it openly. It never suggests claiming it. This connects to the core promise: the only way to strengthen an application is to add real evidence.

## Example output (heuristic mode, fictional profile)

```
must 0.43 4+ years of professional experience with Python  <- partial
must 0.84 Experience building RAG systems with vector DBs  <- full
must 1.00 Solid knowledge of PostgreSQL                    <- full
must 0.42 3+ years of experience running Kubernetes...     <- partial (learning repo only)
nice 1.00 Familiarity with Terraform                       <- full
nice 0.00 Experience with Rust                             <- nothing
SCORE 71.9   must coverage 0.667
```

Kubernetes is correctly weak: the only evidence is a learning repo, and *"I have not run Kubernetes in production"* is rejected.

Python is a limitation of the offline mode. Mira's summary says "6+ years… Python", but with lexical-only retrieval that chunk doesn't make the top 3, and the heuristic can't confirm "4+ years" from a single role's dates. With bge-m3 and a real LLM, which can add up the date ranges, this becomes `full`. The eval in Phase 8 measures exactly this kind of difference.
