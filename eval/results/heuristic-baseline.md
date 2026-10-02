Run 2026-10-02 15:20 UTC · writer `writer:heuristic` · judge `judge:heuristic` · embeddings `hash` · reranker `lexical`

| Metric | Result |
|---|---|
| Requirement extraction F1 (10 postings) | 1.00 ✅ (target >= 0.85) |
| Evidence retrieval Recall@5 (40 pairs) | 0.85 ❌ (target >= 0.9) |
| Score calibration, Spearman vs human rating | 0.84 ✅ (target >= 0.7) |
| **Fabrication recall** (100 planted claims) | 0.79 ❌ (target >= 0.95) |
| False alarm rate (50 correct sentences) | 0.00 ✅ (target <= 0.1) |
| Latency per posting (to review step) | mean 0.27 s, p95 0.57 s |
| LLM calls / tokens per posting | 5 calls, 0 tokens |

| Grounding checks | Fabrication recall | False alarms |
|---|---|---|
| No judge | 0.00 | 0.00 |
| Citations only | 0.00 | 0.00 |
| Code checks (citations + numbers) | 0.46 | 0.00 |
| LLM judge only | 0.33 | 0.00 |
| Full (code + LLM judge) | 0.79 | 0.00 |

| Planted claim type | Recall (full judge) |
|---|---|
| fake_certification | 1.00 |
| learning_to_production | 1.00 |
| number_change | 1.00 |
| outcome_invention | 1.00 |
| scope_inflation | 0.00 |
| seniority | 0.00 |
| tool_injection | 1.00 |
| years_claim | 1.00 |
