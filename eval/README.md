# Evaluation

Everything runs against the fictional sample profile (`sample_profile/`), in an isolated temporary database.

```bash
cd backend
uv sync --group eval
uv run python ../eval/run_eval.py --name my-run        # all suites
uv run python ../eval/run_eval.py --suite fabrication  # one suite
```

The script uses the providers configured in `.env`. Without API keys you measure the **offline heuristic baseline**. With keys you measure the real system.

## Data

| File | What | Size |
|---|---|---|
| `jobs/*.yaml` | Job postings with hand-labeled requirements (`gold`) and a human fit rating (1–5) for the sample profile | 10 |
| `retrieval_pairs.jsonl` | Requirement-style query → text that must be retrieved from the profile | 40 |
| `fabrication_set.jsonl` | Profile sentences with a planted fake claim (8 types), plus correct sentences | 100 + 50 |
| `build_fabrication_set.py` | Regenerates the fabrication set (deterministic) |  |

### Honest limitations
- **The postings are synthetic.** I wrote them for fictional companies with clean headings. That's why the offline heuristic reaches extraction F1 = 1.00, which says more about the test set than about the parser. The spec calls for **30 real postings** (AI Engineer / Backend / Full-stack in Europe). Add them in the same format; real postings have messy structure, mixed responsibilities and requirements, and requirements written as prose.
- 40 retrieval pairs and 10 postings are below the spec's 100 and 30. The numbers are a smoke test, not a benchmark.
- Clean sentences in the fabrication set are verbatim or lightly wrapped profile text. Paraphrased correct sentences would be harder for the judge and would likely raise the false-alarm rate.

### Adding a real posting
Copy the posting text (for your own evaluation only; don't commit copyrighted text you don't have the rights to), then label it:

```yaml
id: acme-ml-engineer
fit_rating: 3            # how well does the sample profile fit, 1-5?
text: |
  ...posting...
gold:
  - { text: "3+ years of Python", importance: must }
  - { text: ["Deutschkenntnisse", "German language skills"], importance: nice }  # variants
```

## Metrics

| Metric | Method |
|---|---|
| Requirement extraction F1 | Greedy one-to-one matching of predicted vs gold requirements by word overlap (Jaccard ≥ 0.5 or high overlap coefficient) |
| Retrieval Recall@5 | A hit if any top-5 chunk contains one of the expected strings |
| Score calibration | Spearman correlation between the fit score and the human rating |
| Fabrication recall | Share of planted claims the grounding checks reject |
| False alarm rate | Share of correct sentences the grounding checks reject |
| Latency / calls / tokens | From each node's trace; for cost details use Langfuse |

The fabrication suite runs as an **ablation**: no judge → citation check → code checks (citations + numbers) → LLM judge alone → everything. That gives the spec's key chart, *recall with and without the judge*.

## Results

See `results/*.md`. The committed `heuristic-baseline` run uses no API keys.
