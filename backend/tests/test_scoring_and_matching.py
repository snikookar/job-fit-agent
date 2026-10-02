from pathlib import Path

import pytest

from jobfit.graph.nodes.fetch_job import fetch_job
from jobfit.graph.nodes.gap_analysis import gap_analysis
from jobfit.graph.nodes.match_evidence import match_evidence
from jobfit.graph.nodes.parse_requirements import parse_requirements
from jobfit.graph.nodes.score import score
from jobfit.graph.services import Services
from jobfit.llm.heuristic import HeuristicLLM, span_years
from jobfit.schemas import Evidence, Requirement
from jobfit.scoring import compute_score, evidence_strength
from tests.fakes import ScriptedLLM

JOB = (Path(__file__).parent / "fixtures" / "ai_engineer_berlin.md").read_text(encoding="utf-8")


def _req(rid, importance, text="x"):
    return Requirement(id=rid, text=text, category="skill", importance=importance)


def _ev(rid, strength):
    return Evidence(requirement_id=rid, chunk_id=f"c-{rid}", quote="q", strength=strength)


# --- deterministic scoring ---------------------------------------------------------


def test_score_weights_must_twice_as_much_as_nice():
    reqs = [_req("r1", "must"), _req("r2", "nice")]
    # only the must is met -> 2 / 3 of the weight
    assert compute_score(reqs, {"r1": [_ev("r1", 1.0)]}).score == pytest.approx(66.7)
    # only the nice is met -> 1 / 3
    assert compute_score(reqs, {"r2": [_ev("r2", 1.0)]}).score == pytest.approx(33.3)


def test_score_uses_best_evidence_and_reports_coverage():
    reqs = [_req("r1", "must"), _req("r2", "must")]
    breakdown = compute_score(reqs, {"r1": [_ev("r1", 0.4), _ev("r1", 0.9)]}, gap_threshold=0.5)
    assert breakdown.items[0].strength == 0.9
    assert breakdown.items[0].contribution == pytest.approx(1.8)
    assert breakdown.must_coverage == 0.5
    assert breakdown.score == pytest.approx(45.0)


def test_score_is_deterministic_and_handles_empty():
    reqs = [_req("r1", "must"), _req("r2", "nice")]
    ev = {"r1": [_ev("r1", 0.7)]}
    assert compute_score(reqs, ev) == compute_score(reqs, ev)
    assert compute_score([], {}).score == 0.0


def test_evidence_strength_is_gated_by_the_verdict():
    assert evidence_strength("none", 1.0) == 0.0  # similar text, but no support
    assert evidence_strength("full", 0.0) == 0.6
    assert evidence_strength("full", 1.0) == 1.0
    assert 0.3 <= evidence_strength("partial", 0.5) <= 0.5


def test_span_years():
    assert span_years("2016 – 2018") == 2
    assert span_years("03/2022 – present", current_year=2026) == 4
    assert span_years(None) is None


# --- nodes ----------------------------------------------------------------------------


def _run_until_gaps(svc):
    state = {"job_text_input": JOB}
    for node in (fetch_job, parse_requirements, match_evidence, score, gap_analysis):
        out = node(state, svc)
        out.pop("trace")
        state.update(out)
    return state


def _req_id(state, startswith):
    return next(
        r["id"] for r in state["requirements"]["requirements"] if r["text"].startswith(startswith)
    )


def test_pipeline_with_heuristic_llm(sample_profile):
    state = _run_until_gaps(Services(writer=HeuristicLLM(), judge=HeuristicLLM("judge")))

    # Terraform is on the resume -> strong evidence that points to a real chunk
    tf = state["evidence"][_req_id(state, "Familiarity with Terraform")]
    assert tf and tf[0]["assessment"] == "full" and tf[0]["chunk_id"].startswith("resume:")

    # "I have not run Kubernetes in production" must not count as evidence
    k8s = state["evidence"][_req_id(state, "3+ years of experience running Kubernetes")]
    assert all("not run Kubernetes" not in e["quote"] for e in k8s)

    # Rust is nowhere in the profile -> gap, and musts are listed before nices
    gap_ids = [g["requirement_id"] for g in state["gaps"]]
    assert _req_id(state, "Experience with Rust") in gap_ids
    importances = [g["importance"] for g in state["gaps"]]
    assert importances == sorted(importances, key=lambda x: x != "must")
    assert 0 < state["score"]["score"] < 100


def test_llm_none_verdict_drops_evidence_and_bad_quotes_are_replaced(sample_profile):
    def assess(ctx):
        items = []
        for p in ctx["pairs"]:
            for i, c in enumerate(p["chunks"]):
                # first chunk: full support but with a made-up quote; others: no support
                items.append(
                    {
                        "requirement_id": p["requirement_id"],
                        "chunk_id": c["chunk_id"],
                        "support": "full" if i == 0 else "none",
                        "quote": "a sentence that is not in the chunk" if i == 0 else "",
                    }
                )
        return {"items": items}

    writer = ScriptedLLM({"assess_evidence": [assess]})
    state = _run_until_gaps(Services(writer=writer, judge=HeuristicLLM("judge")))
    for items in state["evidence"].values():
        assert len(items) <= 1  # only the "full" chunk survives
        for e in items:
            assert e["quote"] != "a sentence that is not in the chunk"
            assert e["assessment"] == "full"
    # one batched call for ~10 requirements, not one call per pair
    assert writer.tasks().count("assess_evidence") == 1
