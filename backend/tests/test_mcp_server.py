import os
import sys

import anyio
import pytest
from mcp import Client, StdioServerParameters

from jobfit import tracker
from jobfit.config import BACKEND_DIR
from jobfit.graph.services import Services
from jobfit.llm.heuristic import HeuristicLLM
from jobfit.mcp_server import create_server
from tests.fakes import ScriptedLLM
from tests.test_grounding import _always_supported, _chunk_with
from tests.test_scoring_and_matching import JOB, _run_until_gaps

TOOLS = {"search_profile", "score_job", "check_claim", "list_tracker_cards"}


def _services(judge=None) -> Services:
    return Services(writer=HeuristicLLM(), judge=judge or HeuristicLLM("judge"))


def _call(name: str, args: dict, svc: Services | None = None):
    """Call a tool through a real MCP client session (in-process transport)."""

    async def go():
        async with Client(create_server(svc or _services())) as client:
            return await client.call_tool(name, args)

    return anyio.run(go)


def _list_tools(server_or_params):
    async def go():
        async with Client(server_or_params) as client:
            return (await client.list_tools()).tools

    return anyio.run(go)


def test_tools_are_listed_read_only_with_bounded_inputs():
    tools = {t.name: t for t in _list_tools(create_server(_services()))}
    assert set(tools) == TOOLS
    assert all(t.annotations.read_only_hint for t in tools.values())
    assert all(t.description for t in tools.values())
    assert tools["search_profile"].input_schema["properties"]["query"]["maxLength"] == 500
    assert tools["score_job"].input_schema["properties"]["job_text"]["maxLength"] == 20_000
    # no tool takes a URL: the server never fetches what a model asks it to
    assert not any("url" in t.input_schema["properties"] for t in tools.values())


def test_search_profile_returns_cited_chunks(sample_profile):
    r = _call("search_profile", {"query": "Terraform infrastructure as code", "k": 3})
    assert not r.is_error
    hits = r.structured_content["result"]
    assert 1 <= len(hits) <= 3
    assert "Terraform" in hits[0]["chunk"]["text"]
    assert hits[0]["chunk"]["id"].startswith("resume:")


@pytest.mark.parametrize(
    "args",
    [{"query": ""}, {"query": "x" * 501}, {"query": "python", "k": 1000}, {"query": "   "}],
)
def test_search_profile_rejects_bad_input(sample_profile, args):
    r = _call("search_profile", args)
    assert r.is_error


def test_score_job_matches_the_graph_and_saves_nothing(sample_profile):
    r = _call("score_job", {"job_text": JOB})
    assert not r.is_error
    report = r.structured_content
    expected = _run_until_gaps(_services())  # the same nodes, run directly
    assert report["score"] == expected["score"]
    assert [g["requirement_id"] for g in report["gaps"]] == [
        g["requirement_id"] for g in expected["gaps"]
    ]
    assert report["offline_mode"] is True
    assert any("Rust" in g["text"] for g in report["gaps"])
    assert tracker.list_applications() == []  # read-only: no tracker card was created


def test_score_job_errors_are_clear():
    empty = _call("score_job", {"job_text": JOB})  # nothing ingested yet
    assert empty.is_error and "profile is empty" in empty.content[0].text
    too_short = _call("score_job", {"job_text": "Python developer"})
    assert too_short.is_error


def test_check_claim_runs_the_three_layers(sample_profile):
    k8s = _chunk_with("learning Kubernetes")
    rabbit = _chunk_with("RabbitMQ")
    judge = ScriptedLLM({"judge": [_always_supported]})
    svc = _services(judge)

    planted = _call(
        "check_claim",
        {"sentence": "Ran Kubernetes in production for 5 years.", "evidence_ids": [k8s]},
        svc,
    ).structured_content
    assert planted["supported"] is False and planted["checks"] == ["numbers"]

    unknown = _call(
        "check_claim", {"sentence": "Built a pipeline.", "evidence_ids": ["resume:999"]}, svc
    ).structured_content
    assert unknown["supported"] is False and unknown["checks"] == ["citations"]

    ok = _call(
        "check_claim",
        {"sentence": "Built an event pipeline with RabbitMQ.", "evidence_ids": [rabbit]},
        svc,
    ).structured_content
    assert ok["supported"] is True
    # only the sentence that passed the deterministic checks reached the LLM judge
    assert judge.tasks() == ["judge"]


def test_check_claim_validates_input(sample_profile):
    no_job = _call(
        "check_claim",
        {
            "sentence": "Your team builds agents.",
            "evidence_ids": ["job"],
            "section": "cover_letter",
        },
    )
    assert no_job.is_error and "job_text" in no_job.content[0].text
    too_many = _call("check_claim", {"sentence": "x", "evidence_ids": ["a"] * 11})
    assert too_many.is_error
    bad_section = _call("check_claim", {"sentence": "x", "evidence_ids": ["a"], "section": "y"})
    assert bad_section.is_error


def test_list_tracker_cards_filters_by_status():
    a = tracker.create_application("AI Engineer", "Acme")
    tracker.create_application("Data Engineer", "Globex")
    tracker.update_application(a["id"], status="applied")

    all_cards = _call("list_tracker_cards", {}).structured_content
    assert {c["title"] for c in all_cards["cards"]} == {"AI Engineer", "Data Engineer"}
    assert all_cards["statuses"][0] == "saved"
    applied = _call("list_tracker_cards", {"status": "applied"}).structured_content
    assert [c["title"] for c in applied["cards"]] == ["AI Engineer"]
    assert _call("list_tracker_cards", {"status": "hired"}).is_error


def test_stdio_server_starts_and_lists_tools():
    """The real entry point as a subprocess: proves nothing but the protocol goes to stdout."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "jobfit.mcp_server"],
        env=dict(os.environ),
        cwd=BACKEND_DIR,
    )
    assert {t.name for t in _list_tools(params)} == TOOLS
