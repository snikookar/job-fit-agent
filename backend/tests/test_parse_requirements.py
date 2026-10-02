from pathlib import Path

import pytest

from jobfit.graph.nodes.parse_requirements import normalize, parse_requirements
from jobfit.graph.services import Services
from jobfit.llm.heuristic import HeuristicLLM
from jobfit.schemas import JobRequirements, Requirement
from tests.fakes import ScriptedLLM

JOB = (Path(__file__).parent / "fixtures" / "ai_engineer_berlin.md").read_text(encoding="utf-8")


def _svc(writer=None):
    return Services(writer=writer or HeuristicLLM(), judge=HeuristicLLM("judge"))


def test_heuristic_extracts_must_and_nice():
    out = parse_requirements({"job_text": JOB, "language": "en", "job_hints": {}}, _svc())
    req = JobRequirements.model_validate(out["requirements"])
    texts = {r.text: r for r in req.requirements}

    assert req.title == "AI Engineer (LLM Platform)"
    assert req.location == "Berlin, Germany"
    assert req.remote == "hybrid"
    assert req.visa_sponsorship == "no"
    # responsibilities and benefits are not requirements
    assert not any("vacation" in t or "evaluation pipeline" in t for t in texts)

    python = texts["4+ years of professional experience with Python"]
    assert python.importance == "must" and python.years == 4 and python.category == "skill"
    assert texts["Familiarity with Terraform"].importance == "nice"
    assert texts["Fluent English"].category == "language"
    assert texts["German language skills"].importance == "nice"
    assert [r.id for r in req.requirements] == [f"r{i}" for i in range(1, len(req.requirements) + 1)]
    assert out["trace"][0]["node"] == "parse_requirements"


def test_node_uses_llm_output_and_normalizes_it():
    llm = ScriptedLLM(
        {
            "parse_requirements": [
                {
                    "title": "",
                    "company": None,
                    "location": None,
                    "requirements": [
                        {"id": "a", "text": "Python", "category": "skill", "importance": "must"},
                        {"id": "b", "text": "python ", "category": "skill", "importance": "must"},
                        {"id": "c", "text": "Go", "category": "skill", "importance": "nice"},
                    ],
                }
            ]
        }
    )
    state = {"job_text": JOB, "language": "en", "job_hints": {"title": "Hinted title", "company": "acme"}}
    out = parse_requirements(state, _svc(llm))
    req = JobRequirements.model_validate(out["requirements"])
    assert [(r.id, r.text) for r in req.requirements] == [("r1", "Python"), ("r2", "Go")]
    assert req.title == "Hinted title" and req.company == "acme"
    # the prompt contains the job text, the context carries the raw inputs
    task, ctx, user_prompt = llm.calls[0]
    assert task == "parse_requirements" and "What you bring" in user_prompt


def test_no_requirements_is_an_error():
    with pytest.raises(ValueError, match="No requirements"):
        normalize(JobRequirements(title="x", requirements=[]), {})


def test_requirement_model_rejects_bad_category():
    with pytest.raises(ValueError):
        Requirement(id="r1", text="x", category="hobby", importance="must")
