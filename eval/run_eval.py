"""Run the evaluation suites against the fictional sample profile.

    cd backend
    uv run python ../eval/run_eval.py                      # all suites
    uv run python ../eval/run_eval.py --suite fabrication  # one suite

Uses whatever providers are configured (.env): with API keys you measure the real
system, without them you measure the offline heuristic baseline. Outputs:

    eval/results/latest.json   all numbers + run metadata
    eval/results/latest.md     summary table (paste into the README)
    eval/results/latest-fabrication.png   recall / false alarms with and without the judge
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import _setup
import yaml

from jobfit.grounding import ALL_LAYERS, judge_draft
from jobfit.textutil import content_terms

TARGETS = {
    "extraction_f1": (">=", 0.85),
    "retrieval_recall_at_5": (">=", 0.90),
    "score_spearman": (">=", 0.70),
    "fabrication_recall": (">=", 0.95),
    "false_alarm_rate": ("<=", 0.10),
}

# --- helpers -------------------------------------------------------------------------------


def _similarity(a: str, b: str) -> float:
    A, B = content_terms(a), content_terms(b)
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return max(inter / len(A | B), 0.8 * inter / min(len(A), len(B)))


def match_requirements(predicted: list[str], gold: list[list[str]], threshold: float = 0.5):
    """Greedy one-to-one matching. A gold item may have several text variants (languages)."""
    pairs = sorted(
        (
            (max(_similarity(p, g) for g in variants), i, j)
            for i, p in enumerate(predicted)
            for j, variants in enumerate(gold)
        ),
        reverse=True,
    )
    used_p, used_g, matches = set(), set(), []
    for sim, i, j in pairs:
        if sim < threshold:
            break
        if i not in used_p and j not in used_g:
            used_p.add(i)
            used_g.add(j)
            matches.append((i, j))
    return matches


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1  # average rank for ties
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float:
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = statistics.mean(ra), statistics.mean(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    var = (sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb)) ** 0.5
    return cov / var if var else 0.0


def _p95(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))] if xs else 0.0


# --- suites ----------------------------------------------------------------------------------


def suite_pipeline(limit: int | None) -> dict:
    """Run every labeled job to the review step: extraction F1, score calibration, latency."""
    from jobfit.graph.runner import JobFitAgent

    agent = JobFitAgent()
    jobs = [
        yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted((_setup.EVAL_DIR / "jobs").glob("*.yaml"))
    ]
    jobs = jobs[:limit] if limit else jobs

    tp = fp = fn = importance_ok = 0
    per_job, scores, ratings, seconds, calls, tokens = [], [], [], [], [], []
    for job in jobs:
        start = time.perf_counter()
        events = list(agent.start(job["id"], job_text=job["text"]))
        elapsed = time.perf_counter() - start
        if events[-1].type == "error":
            per_job.append({"id": job["id"], "error": events[-1].data["message"]})
            continue
        state = agent.state(job["id"]) or {}
        reqs = state["requirements"]["requirements"]
        predicted = [r["text"] for r in reqs]
        gold = [g["text"] if isinstance(g["text"], list) else [g["text"]] for g in job["gold"]]
        matches = match_requirements(predicted, gold)
        tp += len(matches)
        fp += len(predicted) - len(matches)
        fn += len(gold) - len(matches)
        importance_ok += sum(
            1 for i, j in matches if reqs[i]["importance"] == job["gold"][j]["importance"]
        )

        score = state["score"]["score"]
        scores.append(score)
        ratings.append(job["fit_rating"])
        trace = state.get("trace") or []
        seconds.append(elapsed)
        calls.append(sum(t.get("llm_calls", 0) for t in trace))
        tokens.append(sum(t.get("tokens", 0) for t in trace))
        per_job.append(
            {
                "id": job["id"],
                "fit_rating": job["fit_rating"],
                "score": score,
                "predicted": len(predicted),
                "gold": len(gold),
                "matched": len(matches),
                "writer_rounds": state.get("revision"),
                "removed_sentences": len(state.get("removed") or []),
                "seconds": round(elapsed, 2),
            }
        )
        print(
            f"  {job['id']:<28} score {score:5.1f}  human {job['fit_rating']}  matched {len(matches)}/{len(gold)}"
        )

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "extraction_precision": round(precision, 3),
        "extraction_recall": round(recall, 3),
        "extraction_f1": round(2 * precision * recall / (precision + recall), 3)
        if precision + recall
        else 0.0,
        "importance_accuracy": round(importance_ok / tp, 3) if tp else 0.0,
        "score_spearman": round(spearman(scores, ratings), 3) if len(scores) > 2 else None,
        "latency_mean_s": round(statistics.mean(seconds), 2) if seconds else None,
        "latency_p95_s": round(_p95(seconds), 2) if seconds else None,
        "llm_calls_mean": round(statistics.mean(calls), 1) if calls else None,
        "tokens_mean": round(statistics.mean(tokens)) if tokens else None,
        "jobs": per_job,
    }


def suite_retrieval() -> dict:
    from jobfit.retrieval.search import HybridRetriever

    retriever = HybridRetriever()
    pairs = [
        json.loads(line)
        for line in (_setup.EVAL_DIR / "retrieval_pairs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    hits_at_1 = hits_at_5 = 0
    rr_sum = 0.0
    misses = []
    for pair in pairs:
        hits = retriever.search(pair["query"], k=5)
        ranks = [
            rank
            for rank, h in enumerate(hits, start=1)
            if any(
                e.lower() in f"{h.chunk.section} {h.chunk.text}".lower() for e in pair["expected"]
            )
        ]
        if ranks:
            hits_at_5 += 1
            hits_at_1 += ranks[0] == 1
            rr_sum += 1 / ranks[0]
        else:
            misses.append(pair["query"])
    n = len(pairs)
    return {
        "retrieval_pairs": n,
        "retrieval_recall_at_1": round(hits_at_1 / n, 3),
        "retrieval_recall_at_5": round(hits_at_5 / n, 3),
        "retrieval_mrr": round(rr_sum / n, 3),
        "retrieval_misses": misses,
    }


FAB_CONFIGS = [
    ("No judge", frozenset()),
    ("Citations only", frozenset({"citations"})),
    ("Code checks\n(citations + numbers)", frozenset({"citations", "numbers"})),
    ("LLM judge only", frozenset({"llm"})),
    ("Full\n(code + LLM judge)", ALL_LAYERS),
]


def suite_fabrication(batch: int = 10) -> dict:
    from jobfit.llm import get_judge_llm
    from jobfit.schemas import Draft

    judge = get_judge_llm()
    cases = [
        json.loads(line)
        for line in (_setup.EVAL_DIR / "fabrication_set.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]

    def flagged_ids(layers: frozenset[str]) -> set[str]:
        if not layers:
            return set()  # without a judge every sentence reaches the user
        flagged = set()
        for start in range(0, len(cases), batch):
            group = cases[start : start + batch]
            # One draft per batch, like a real draft with ~10 sentences.
            draft = Draft(
                bullets=[
                    {"text": c["text"], "evidence_ids": c["evidence_ids"]}
                    for c in group
                    if c["section"] == "bullets"
                ],
                cover_letter=[
                    {"text": c["text"], "evidence_ids": c["evidence_ids"]}
                    for c in group
                    if c["section"] == "cover_letter"
                ],
            )
            verdicts = judge_draft(draft, "", judge, layers=layers)
            by_pos = {(v.section, v.index): v for v in verdicts}
            counters = {"bullets": 0, "cover_letter": 0}
            for c in group:
                v = by_pos[(c["section"], counters[c["section"]])]
                counters[c["section"]] += 1
                if not v.supported:
                    flagged.add(c["id"])
        return flagged

    fabricated = [c for c in cases if c["label"] == "fabricated"]
    clean = [c for c in cases if c["label"] == "clean"]
    configs = []
    full_flagged: set[str] = set()
    for name, layers in FAB_CONFIGS:
        flagged = flagged_ids(layers)
        if layers == ALL_LAYERS:
            full_flagged = flagged
        configs.append(
            {
                "config": name.replace("\n", " "),
                "label": name,
                "recall": round(sum(c["id"] in flagged for c in fabricated) / len(fabricated), 3),
                "false_alarm_rate": round(sum(c["id"] in flagged for c in clean) / len(clean), 3),
            }
        )
        print(
            f"  {name.replace(chr(10), ' '):<36} recall {configs[-1]['recall']:.2f}  false alarms {configs[-1]['false_alarm_rate']:.2f}"
        )

    by_mutation: dict[str, list[bool]] = {}
    for c in fabricated:
        by_mutation.setdefault(c["mutation"], []).append(c["id"] in full_flagged)
    full = configs[-1]
    return {
        "fabrication_cases": len(fabricated),
        "clean_cases": len(clean),
        "fabrication_recall": full["recall"],
        "false_alarm_rate": full["false_alarm_rate"],
        "fabrication_by_config": configs,
        "fabrication_recall_by_mutation": {
            k: round(sum(v) / len(v), 3) for k, v in sorted(by_mutation.items())
        },
        "missed_fabrications": [c["text"] for c in fabricated if c["id"] not in full_flagged][:20],
        "false_alarms": [c["text"] for c in clean if c["id"] in full_flagged][:20],
    }


# --- reporting -------------------------------------------------------------------------------


def plot_fabrication(configs: list[dict], meta: dict, path: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  (matplotlib not installed: `uv sync --group eval` to get the chart)")
        return False
    labels = [c["label"] for c in configs]
    x = range(len(configs))
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=150)
    w = 0.38
    b1 = ax.bar(
        [i - w / 2 for i in x],
        [c["recall"] for c in configs],
        w,
        label="Fabrications caught (recall)",
        color="#2a7f62",
    )
    b2 = ax.bar(
        [i + w / 2 for i in x],
        [c["false_alarm_rate"] for c in configs],
        w,
        label="Correct sentences rejected (false alarms)",
        color="#c8553d",
    )
    ax.bar_label(b1, fmt="%.2f", fontsize=8)
    ax.bar_label(b2, fmt="%.2f", fontsize=8)
    ax.axhline(0.95, ls="--", lw=1, color="#2a7f62", alpha=0.6)
    ax.axhline(0.10, ls="--", lw=1, color="#c8553d", alpha=0.6)
    ax.set_xticks(list(x), labels, fontsize=8)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("rate")
    ax.set_title(
        f"Fabrication detection with and without the judge\njudge: {meta['judge']}", fontsize=10
    )
    ax.legend(fontsize=8, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def to_markdown(results: dict, meta: dict) -> str:
    def fmt(key: str) -> str:
        v = results.get(key)
        if v is None:
            return "–"
        op, target = TARGETS[key]
        ok = v >= target if op == ">=" else v <= target
        return f"{v:.2f} {'✅' if ok else '❌'} (target {op} {target})"

    lines = [
        f"Run {meta['date']} · writer `{meta['writer']}` · judge `{meta['judge']}` · embeddings `{meta['embedder']}` · reranker `{meta['reranker']}`",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Requirement extraction F1 ({meta.get('jobs', '?')} postings) | {fmt('extraction_f1')} |",
        f"| Evidence retrieval Recall@5 ({results.get('retrieval_pairs', '?')} pairs) | {fmt('retrieval_recall_at_5')} |",
        f"| Score calibration, Spearman vs human rating | {fmt('score_spearman')} |",
        f"| **Fabrication recall** ({results.get('fabrication_cases', '?')} planted claims) | {fmt('fabrication_recall')} |",
        f"| False alarm rate ({results.get('clean_cases', '?')} correct sentences) | {fmt('false_alarm_rate')} |",
    ]
    if results.get("latency_mean_s") is not None:
        lines.append(
            f"| Latency per posting (to review step) | mean {results['latency_mean_s']} s, p95 {results['latency_p95_s']} s |"
        )
        lines.append(
            f"| LLM calls / tokens per posting | {results['llm_calls_mean']} calls, {results['tokens_mean']} tokens |"
        )
    if results.get("fabrication_by_config"):
        lines += ["", "| Grounding checks | Fabrication recall | False alarms |", "|---|---|---|"]
        for c in results["fabrication_by_config"]:
            lines.append(f"| {c['config']} | {c['recall']:.2f} | {c['false_alarm_rate']:.2f} |")
        lines += ["", "| Planted claim type | Recall (full judge) |", "|---|---|"]
        for k, v in results["fabrication_recall_by_mutation"].items():
            lines.append(f"| {k} | {v:.2f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--suite", choices=["all", "pipeline", "retrieval", "fabrication"], default="all"
    )
    parser.add_argument("--limit", type=int, help="only the first N job postings")
    parser.add_argument(
        "--name", default="latest", help="results file name (eval/results/<name>.json)"
    )
    args = parser.parse_args()

    _setup.load_profile()
    from jobfit.llm import get_judge_llm, get_writer_llm
    from jobfit.retrieval.embeddings import get_embedder
    from jobfit.retrieval.rerank import get_reranker

    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
    except OSError:
        commit = ""
    meta = {
        "date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "commit": commit,
        "writer": get_writer_llm().name,
        "judge": get_judge_llm().name,
        "embedder": get_embedder().name,
        "reranker": get_reranker().name,
    }
    results: dict = {}
    if args.suite in ("all", "pipeline"):
        print("pipeline (extraction, calibration, latency)")
        results.update(suite_pipeline(args.limit))
        meta["jobs"] = len(results["jobs"])
    if args.suite in ("all", "retrieval"):
        print("retrieval")
        results.update(suite_retrieval())
    if args.suite in ("all", "fabrication"):
        print("fabrication")
        results.update(suite_fabrication())

    out = _setup.RESULTS_DIR
    out.mkdir(exist_ok=True)
    (out / f"{args.name}.json").write_text(
        json.dumps({"meta": meta, "results": results}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md = to_markdown(results, meta)
    (out / f"{args.name}.md").write_text(md, encoding="utf-8")
    if results.get("fabrication_by_config"):
        plot_fabrication(
            results["fabrication_by_config"], meta, out / f"{args.name}-fabrication.png"
        )
    print("\n" + md)


if __name__ == "__main__":
    main()
