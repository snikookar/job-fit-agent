from pathlib import Path

from jobfit.graph.nodes.fetch_job import fetch_job
from jobfit.graph.nodes.gap_analysis import gap_analysis
from jobfit.graph.nodes.grounding_judge import grounding_judge, route_after_judge
from jobfit.graph.nodes.match_evidence import match_evidence
from jobfit.graph.nodes.parse_requirements import parse_requirements
from jobfit.graph.nodes.score import score
from jobfit.graph.nodes.writer import writer
from jobfit.graph.services import Services
from jobfit.grounding import judge_draft
from jobfit.llm.heuristic import HeuristicLLM
from jobfit.retrieval import store
from jobfit.schemas import Draft
from tests.fakes import ScriptedLLM

JOB = (Path(__file__).parent / "fixtures" / "ai_engineer_berlin.md").read_text(encoding="utf-8")


def _chunk_with(text: str) -> str:
    return next(c.id for c in store.list_chunks() if text in c.text)


def _draft(bullets=(), letter=()) -> Draft:
    return Draft.model_validate(
        {
            "bullets": [{"text": t, "evidence_ids": ids} for t, ids in bullets],
            "cover_letter": [{"text": t, "evidence_ids": ids} for t, ids in letter],
        }
    )


def _always_supported(ctx):
    return {
        "items": [
            {
                "section": s["section"],
                "index": s["index"],
                "supported": True,
                "confidence": 0.9,
                "reason": "ok",
            }
            for s in ctx["sentences"]
        ]
    }


# --- deterministic layers ----------------------------------------------------------------


def test_citation_checks(sample_profile):
    rabbit = _chunk_with("RabbitMQ")
    draft = _draft(
        bullets=[
            ("Built an event pipeline with RabbitMQ.", []),
            ("Built an event pipeline with RabbitMQ.", ["resume:999"]),
            ("Built an event pipeline with RabbitMQ.", ["job"]),
            ("Built an event pipeline with RabbitMQ.", [rabbit]),
        ]
    )
    judge = ScriptedLLM({"judge": [_always_supported]})
    verdicts = judge_draft(draft, JOB, judge)
    assert [v.supported for v in verdicts] == [False, False, False, True]
    assert all(v.checks == ["citations"] for v in verdicts[:3])
    assert "doesn't exist" in verdicts[1].reason
    # only the sentence that passed the cheap checks was sent to the LLM
    assert len(judge.calls) == 1 and len(judge.calls[0][1]["sentences"]) == 1


def test_number_check_catches_planted_numbers(sample_profile):
    k8s = _chunk_with("learning Kubernetes")
    mentor = _chunk_with("Mentored two junior engineers")
    draft = _draft(
        bullets=[
            ("Ran Kubernetes in production for 5 years.", [k8s]),
            ("Mentored 2 junior engineers.", [mentor]),  # "two" in the evidence == 2
        ]
    )
    verdicts = judge_draft(draft, JOB, ScriptedLLM({"judge": [_always_supported]}))
    assert verdicts[0].supported is False and verdicts[0].checks == ["numbers"]
    assert "5" in verdicts[0].reason
    assert verdicts[1].supported is True


# --- LLM layer --------------------------------------------------------------------------


def test_threshold_and_missing_verdicts(sample_profile):
    rabbit = _chunk_with("RabbitMQ")
    draft = _draft(bullets=[("Built a pipeline with RabbitMQ.", [rabbit])] * 3)

    def judge_fn(ctx):
        return {
            "items": [
                {
                    "section": "bullets",
                    "index": 0,
                    "supported": True,
                    "confidence": 0.9,
                    "reason": "ok",
                },
                {
                    "section": "bullets",
                    "index": 1,
                    "supported": True,
                    "confidence": 0.3,
                    "reason": "unsure",
                },
                # index 2 missing on purpose
            ]
        }

    verdicts = judge_draft(draft, JOB, ScriptedLLM({"judge": [judge_fn]}), threshold=0.5)
    assert [v.supported for v in verdicts] == [True, False, False]
    assert verdicts[1].p_supported == 0.3
    assert "no verdict" in verdicts[2].reason


def test_unchanged_supported_sentences_are_not_rejudged(sample_profile):
    rabbit = _chunk_with("RabbitMQ")
    draft = _draft(bullets=[("Built a pipeline with RabbitMQ.", [rabbit])])
    first = judge_draft(draft, JOB, ScriptedLLM({"judge": [_always_supported]}))
    judge = ScriptedLLM({"judge": [_always_supported]})
    second = judge_draft(draft, JOB, judge, cache=first)
    assert second[0].supported and judge.calls == []


def test_heuristic_judge_catches_invented_technology(sample_profile):
    rabbit = _chunk_with("RabbitMQ")
    draft = _draft(
        bullets=[("Built an event pipeline with RabbitMQ and Kafka on Kubernetes.", [rabbit])],
        letter=[("I led the Kubernetes migration at my last company.", ["job"])],
    )
    verdicts = judge_draft(draft, JOB, HeuristicLLM("judge"))
    assert not verdicts[0].supported and "Kafka" in verdicts[0].reason
    assert not verdicts[1].supported  # a candidate claim backed only by the job posting


# --- the writer <-> judge loop --------------------------------------------------------------


def _state_until_gaps(svc):
    state = {"job_text_input": JOB}
    for node in (fetch_job, parse_requirements, match_evidence, score, gap_analysis):
        out = node(state, svc)
        out.pop("trace")
        state.update(out)
    return state


def _step(state, node, svc):
    out = node(state, svc)
    out.pop("trace")
    state.update(out)


def test_loop_fixes_unsupported_sentence_in_second_round(sample_profile):
    rabbit = _chunk_with("RabbitMQ")
    good = {"text": "Built an event pipeline with RabbitMQ.", "evidence_ids": [rabbit]}
    fake = {"text": "Ran Kubernetes in production for 5 years.", "evidence_ids": [rabbit]}
    writer_llm = ScriptedLLM(
        {
            "write_draft": [
                {"bullets": [good, fake], "cover_letter": []},
                {"bullets": [good], "cover_letter": []},
            ]
        }
    )
    svc = Services(writer=writer_llm, judge=ScriptedLLM({"judge": [_always_supported]}))
    state = _state_until_gaps(svc)

    _step(state, writer, svc)
    _step(state, grounding_judge, svc)
    assert route_after_judge(state) == "writer"
    assert state["removed"] == []

    _step(state, writer, svc)
    # the second writer call saw the judge's feedback
    assert "UNSUPPORTED" in writer_llm.calls[-1][2]
    _step(state, grounding_judge, svc)
    assert route_after_judge(state) == "human_review"
    assert state["revision"] == 2


def test_loop_removes_sentences_still_unsupported_after_last_round(sample_profile):
    rabbit = _chunk_with("RabbitMQ")
    good = {"text": "Built an event pipeline with RabbitMQ.", "evidence_ids": [rabbit]}
    fake = {"text": "Ran Kubernetes in production for 5 years.", "evidence_ids": [rabbit]}
    stubborn = ScriptedLLM({"write_draft": [{"bullets": [fake, good], "cover_letter": []}]})
    svc = Services(writer=stubborn, judge=ScriptedLLM({"judge": [_always_supported]}))
    state = _state_until_gaps(svc)

    for _ in range(2):  # MAX_DRAFT_ROUNDS = 2
        _step(state, writer, svc)
        _step(state, grounding_judge, svc)

    assert route_after_judge(state) == "human_review"
    assert [s["text"] for s in state["draft"]["bullets"]] == [good["text"]]
    assert [v["text"] for v in state["removed"]] == [fake["text"]]
    assert state["verdicts"][0]["index"] == 0  # re-indexed to the trimmed draft


def test_full_heuristic_round_produces_grounded_draft(sample_profile):
    svc = Services(writer=HeuristicLLM(), judge=HeuristicLLM("judge"))
    state = _state_until_gaps(svc)
    for _ in range(2):
        _step(state, writer, svc)
        _step(state, grounding_judge, svc)
        if route_after_judge(state) == "human_review":
            break
    assert route_after_judge(state) == "human_review"
    assert state["draft"]["bullets"], "the draft should keep supported bullets"
    for section in ("bullets", "cover_letter"):
        for s in state["draft"][section]:
            assert s["evidence_ids"], "every sentence must cite evidence"
