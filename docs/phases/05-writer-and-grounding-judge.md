# Phase 5: `writer` + `grounding_judge`

**Goal:** the core promise, *"a resume tailoring tool that won't let you lie"*. Every generated sentence cites evidence, and a separate judge rejects any sentence the evidence doesn't support.

```
           ┌──────────────────────────────── feedback: which sentences failed and why ┐
           ▼                                                                           │
writer ──► Draft (every sentence has evidence_ids) ──► grounding_judge ── unsupported ─┤
                                                         │                rounds left? │
                                                         │ all supported   no ─► remove them,
                                                         ▼                       report them
                                                    human_review ◄──────────────────────┘
```

## Files created

| File | Purpose |
|---|---|
| `jobfit/graph/nodes/writer.py` | Builds an evidence pool (unique chunks, strongest first) and asks for bullets + cover letter. On round 2 it includes the judge's feedback |
| `jobfit/grounding.py` | The three-layer check: `judge_draft()`, plus `drop_unsupported()` |
| `jobfit/graph/nodes/grounding_judge.py` | Runs the checks, decides the loop (`route_after_judge`), and removes what's still unsupported after the last round |
| `jobfit/graph/prompts/writer.md`, `judge.md` | Prompts |
| `jobfit/schemas.py` (extended) | `JudgeItem`, `JudgeResult`, `JOB_EVIDENCE_ID = "job"`, and `Verdict.evidence_ids` |
| `jobfit/llm/heuristic.py` (extended) | Offline writer (reuses evidence wording) and judge (tech-tag and term coverage) |
| `tests/test_grounding.py` | Each layer, the threshold, the verdict cache, and both loop exits |

## Design decisions

### Three layers, cheapest first ("defense in depth")
| Layer | Catches | Cost |
|---|---|---|
| **1. Citations** (code) | Missing citations, made-up chunk IDs, resume bullets that cite only the job posting | Free |
| **2. Numbers** (code) | "5 years", "40%", "team of 12" not present in the cited evidence. Number words are normalized ("two" = 2) | Free |
| **3. LLM judge** (different model) | Inflated scope ("contributed" → "led"), invented tools, paraphrased fabrications, "learning project" → "in production" | 1 call per round |

Why not just the LLM judge? LLMs are bad at noticing a *changed number* in fluent text, and that's exactly the most common fabrication ("3 years" → "5 years"). A regex can't miss it. The deterministic layers also mean sentences that are obviously broken never cost a judge call. And the judge model can't "approve" a sentence that cites a chunk ID that doesn't exist.

Why not code only? Code can't tell that *"Led the platform team"* overstates *"Mentored two junior engineers"*. That needs language understanding.

### A different model as judge
If the same model writes and judges, it tends to accept its own mistakes: the same training gives it the same blind spots. The defaults are **DeepSeek** (writer) and **GLM** (judge). The judge also runs at temperature 0 for repeatability. Phase 8 measures how much the judge adds.

### Confidence + threshold, not just yes/no
The judge returns `supported` and a `confidence`. The code turns those into `P(supported)` and compares it with `JUDGE_THRESHOLD` (default 0.5). This answers the spec's risk *"Judge is too strict → measure false alarms and tune the threshold"*: you change one number in `.env`, and the eval shows the recall vs false-alarm trade-off.

### The job posting as evidence: `"job"`
A cover letter needs sentences like *"I'm applying for the AI Engineer role at Flintwave"*, which are true but not in the profile. These may cite the special ID `"job"`. The rules prevent abuse:
- Resume bullets can **never** cite only `"job"` (deterministic check).
- The judge prompt says that claims about the candidate can't be supported by the job posting.
- Greetings and sign-offs aren't generated at all. The export template adds them.

### Strict by default
- If the judge returns no verdict for a sentence, it counts as **unsupported**.
- Any unknown chunk ID means **unsupported**.
- If the evidence is insufficient, the writer is told that fewer well-supported sentences are better.

### The loop: at most 2 rounds (spec)
`MAX_DRAFT_ROUNDS=2` gives *write → judge → rewrite → judge*. In round 2 the writer sees every sentence marked SUPPORTED or UNSUPPORTED with the reason. It must keep supported sentences exactly as they are and fix or delete the others.

After the last round, still-unsupported sentences are **removed** and stored in `state["removed"]`, so the UI can show the user what was cut and why.

**Verdict cache:** supported sentences that are unchanged (same text, same citations) aren't sent to the judge again in round 2. That's cheaper, and the results stay stable.
