import json
import time

import pytest
from fastapi.testclient import TestClient

from jobfit.api.main import create_app
from jobfit.graph.services import Services
from jobfit.llm.heuristic import HeuristicLLM
from tests.test_graph import JOB


@pytest.fixture
def client():
    app = create_app(Services(writer=HeuristicLLM(), judge=HeuristicLLM("judge")))
    with TestClient(app) as c:
        yield c


def _sse(client, run_id, after=-1) -> list[dict]:
    events = []
    with client.stream("GET", f"/api/jobs/{run_id}/events", params={"after": after}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data:"):
                payload = json.loads(line[5:].strip())
                if payload:
                    events.append(payload)
            if line.startswith("event: end"):
                break
    return events


def _wait_status(client, run_id, status, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/jobs/{run_id}").json()
        if body["run"]["status"] == status and not body["active"]:
            return body
        time.sleep(0.1)
    raise AssertionError(f"run never reached {status}")


def test_health_reports_offline_mode(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["offline_mode"] is True
    assert body["database"] in ("sqlite", "postgresql")


def test_profile_endpoints(client, sample_profile_dir):
    assert client.get("/api/profile").json()["total_chunks"] == 0

    pdf = (sample_profile_dir / "resume.pdf").read_bytes()
    r = client.post("/api/profile/resume", files={"file": ("resume.pdf", pdf, "application/pdf")})
    assert r.status_code == 200 and r.json()["chunks"] > 15

    md = (sample_profile_dir / "projects" / "support-copilot.md").read_bytes()
    r = client.post(
        "/api/profile/projects", files=[("files", ("support-copilot.md", md, "text/markdown"))]
    )
    assert r.json() == [{"source": "project:support-copilot", "chunks": 4}]

    bad = client.post(
        "/api/profile/resume", files={"file": ("cv.exe", b"MZ", "application/octet-stream")}
    )
    assert bad.status_code == 400

    profile = client.get("/api/profile").json()
    assert {s["source"] for s in profile["sources"]} == {"resume", "project:support-copilot"}
    chunk_id = client.get(
        "/api/profile/chunks", params={"source": "project:support-copilot"}
    ).json()[0]["id"]
    assert client.get(f"/api/profile/chunks/{chunk_id}").json()["id"] == chunk_id

    client.put("/api/profile/info", json={"name": "Mira Lindqvist", "email": "m@example.com"})
    assert client.get("/api/profile").json()["info"]["name"] == "Mira Lindqvist"

    client.delete("/api/profile/sources/project:support-copilot")
    assert {s["source"] for s in client.get("/api/profile").json()["sources"]} == {"resume"}


def test_full_job_flow_over_http(client):
    client.post("/api/profile/sample")
    run_id = client.post("/api/jobs", json={"text": JOB}).json()["run_id"]

    events = _sse(client, run_id)
    assert [e["node"] for e in events if e["type"] == "node"][:3] == [
        "fetch_job",
        "parse_requirements",
        "match_evidence",
    ]
    assert events[-1]["type"] == "interrupt"

    body = _wait_status(client, run_id, "awaiting_review")
    assert body["run"]["title"] == "AI Engineer (LLM Platform)" and body["run"]["score"] > 0
    state = body["state"]
    assert state["awaiting_review"] is True
    cited = {i for s in state["draft"]["bullets"] for i in s["evidence_ids"]}
    assert cited <= set(body["chunks"])  # the UI can show every cited chunk

    # check an edit before approving: a planted number is flagged
    draft = state["draft"]
    draft["bullets"][0] = {
        **draft["bullets"][0],
        "text": draft["bullets"][0]["text"] + " Over 9 years.",
    }
    verdicts = client.post(f"/api/jobs/{run_id}/check", json={"draft": draft}).json()
    assert verdicts[0]["supported"] is False and "numbers" in verdicts[0]["checks"]

    assert client.post(f"/api/jobs/{run_id}/review", json={"approved": True}).status_code == 202
    events = _sse(client, run_id, after=events[-1]["seq"])
    assert events[-1]["type"] == "done"
    _wait_status(client, run_id, "done")

    doc = client.get(f"/api/jobs/{run_id}/docx")
    assert doc.status_code == 200 and doc.content[:2] == b"PK"  # .docx is a zip file

    # reviewing twice is a conflict
    assert client.post(f"/api/jobs/{run_id}/review", json={"approved": True}).status_code == 409

    jobs = client.get("/api/jobs").json()
    assert jobs[0]["run_id"] == run_id and jobs[0]["status"] == "done"


def test_tracker_endpoints(client):
    app = client.post("/api/tracker", json={"title": "ML Engineer", "company": "Example"}).json()
    assert app["status"] == "saved"
    assert (
        client.patch(f"/api/tracker/{app['id']}", json={"status": "interview"}).json()["status"]
        == "interview"
    )
    assert client.patch(f"/api/tracker/{app['id']}", json={"status": "ghosted"}).status_code == 400
    listing = client.get("/api/tracker").json()
    assert listing["statuses"] == ["saved", "applied", "interview", "offer", "rejected"]
    assert client.delete(f"/api/tracker/{app['id']}").status_code == 200
    assert client.get("/api/tracker").json()["applications"] == []


def test_job_validation_and_failed_run(client):
    assert client.post("/api/jobs", json={}).status_code == 422
    run_id = client.post("/api/jobs", json={"url": "https://www.linkedin.com/jobs/view/1"}).json()[
        "run_id"
    ]
    events = _sse(client, run_id)
    assert events[-1]["type"] == "error"
    body = _wait_status(client, run_id, "failed")
    assert "paste" in body["run"]["error"]
