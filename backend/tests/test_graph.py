from pathlib import Path

import docx
import pytest

from jobfit import tracker
from jobfit.export.docx import build_docx
from jobfit.graph.checkpoint import make_checkpointer
from jobfit.graph.graph import NODE_ORDER
from jobfit.graph.runner import JobFitAgent
from jobfit.graph.services import Services
from jobfit.llm.heuristic import HeuristicLLM
from jobfit.schemas import Draft, DraftSentence, JobRequirements, ReviewDecision
from tests.fakes import ScriptedLLM

JOB = (Path(__file__).parent / "fixtures" / "ai_engineer_berlin.md").read_text(encoding="utf-8")


@pytest.fixture
def agent(sample_profile):
    return JobFitAgent(Services(writer=HeuristicLLM(), judge=HeuristicLLM("judge")))


def _start(agent, run_id="run1"):
    return list(agent.start(run_id, job_text=JOB))


def test_run_pauses_for_review_then_exports(agent):
    events = _start(agent)
    nodes = [e.node for e in events if e.type == "node"]
    assert nodes == NODE_ORDER[: NODE_ORDER.index("human_review")]
    assert events[-1].type == "interrupt"
    assert events[-1].data["value"]["draft"]["bullets"]

    state = agent.state("run1")
    assert state["awaiting_review"] is True
    assert "docx_path" not in state
    assert tracker.list_applications() == []  # nothing is logged before approval

    events = list(agent.resume("run1", ReviewDecision(approved=True)))
    assert [e.node for e in events if e.type == "node"] == ["human_review", "export"]
    assert events[-1].type == "done"

    state = agent.state("run1")
    assert state["awaiting_review"] is False
    assert Path(state["docx_path"]).exists()
    apps = tracker.list_applications()
    assert len(apps) == 1 and apps[0]["status"] == "saved" and apps[0]["has_docx"]
    assert apps[0]["title"] == "AI Engineer (LLM Platform)"
    # every node recorded timing info
    assert {t["node"] for t in state["trace"]} == set(NODE_ORDER)


def test_review_survives_a_restart(sample_profile):
    svc = Services(writer=HeuristicLLM(), judge=HeuristicLLM("judge"))
    first = JobFitAgent(svc)
    _start(first, "persist")
    # a brand new agent + checkpointer, as after a server restart
    second = JobFitAgent(svc, make_checkpointer())
    assert second.state("persist")["awaiting_review"] is True
    events = list(second.resume("persist", ReviewDecision(approved=True)))
    assert events[-1].type == "done"


def test_unsupported_user_edits_are_removed_unless_kept(agent):
    _start(agent)
    draft = Draft.model_validate(agent.state("run1")["draft"])
    good_bullet = draft.bullets[0]
    fabricated = DraftSentence(
        text="Led a team of 15 engineers running Kubernetes in production.",
        evidence_ids=good_bullet.evidence_ids,
    )
    edited = draft.model_copy(update={"bullets": [good_bullet, fabricated]})

    list(agent.resume("run1", ReviewDecision(approved=True, draft=edited)))
    state = agent.state("run1")
    assert [b["text"] for b in state["final_draft"]["bullets"]] == [good_bullet.text]
    removed = [r for r in state["removed"] if r.get("edited_by_user")]
    assert removed and removed[0]["text"] == fabricated.text

    # the user can keep an edit on purpose; it stays flagged
    _start(agent, "run2")
    list(
        agent.resume(
            "run2", ReviewDecision(approved=True, draft=edited, keep_unsupported_edits=True)
        )
    )
    state = agent.state("run2")
    assert len(state["final_draft"]["bullets"]) == 2
    assert any(not v["supported"] for v in state["final_verdicts"])


def test_rejected_draft_is_tracked_without_document(agent):
    _start(agent)
    list(agent.resume("run1", ReviewDecision(approved=False, note="not a fit")))
    state = agent.state("run1")
    assert state["approved"] is False and "docx_path" not in state
    assert tracker.list_applications()[0]["has_docx"] is False


def test_fetch_error_becomes_an_error_event(sample_profile):
    agent = JobFitAgent(Services(writer=HeuristicLLM(), judge=HeuristicLLM("judge")))
    events = list(agent.start("bad", job_url="https://www.linkedin.com/jobs/view/1"))
    assert events[-1].type == "error"
    assert events[-1].node == "fetch_job"
    assert "paste" in events[-1].data["message"]


def test_writer_judge_loop_runs_inside_the_graph(sample_profile):
    from jobfit.retrieval import store

    rabbit = next(c.id for c in store.list_chunks() if "RabbitMQ" in c.text)
    good = {"text": "Built an event pipeline with RabbitMQ.", "evidence_ids": [rabbit]}
    fake = {"text": "Ran Kubernetes for 5 years.", "evidence_ids": [rabbit]}
    writer = ScriptedLLM({"write_draft": [{"bullets": [good, fake], "cover_letter": []}]})
    agent = JobFitAgent(Services(writer=writer, judge=HeuristicLLM("judge")))
    events = _start(agent)
    assert [e.node for e in events if e.node in ("writer", "grounding_judge")] == [
        "writer",
        "grounding_judge",
        "writer",
        "grounding_judge",
    ]
    state = agent.state("run1")
    assert [v["text"] for v in state["removed"]] == [fake["text"]]


def test_docx_with_evidence_comments(tmp_path, sample_profile):
    from jobfit.retrieval import store

    chunk = store.list_chunks("resume")[3]
    draft = Draft(
        bullets=[DraftSentence(text=chunk.text, evidence_ids=[chunk.id])],
        cover_letter=[
            DraftSentence(text="Ich bewerbe mich als Data Engineer.", evidence_ids=["job"])
        ],
    )
    job = JobRequirements(title="Data Engineer", company="Beispiel GmbH", requirements=[])
    path = build_docx(
        draft,
        job,
        {"name": "Mira Lindqvist", "email": "mira@example.com"},
        tmp_path / "a.docx",
        language="de",
        evidence={chunk.id: chunk},
        evidence_comments=True,
    )
    d = docx.Document(str(path))
    texts = [p.text for p in d.paragraphs]
    assert "Sehr geehrte Damen und Herren," in texts and "Mit freundlichen Grüßen" in texts
    assert chunk.text in texts
    assert len(list(d.comments)) == 2
