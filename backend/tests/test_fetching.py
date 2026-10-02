import json

import httpx
import pytest

from jobfit.fetching import FetchError, fetch_url, from_pasted_text, html_to_text

LONG_PAGE = """<html><head><title>Backend Engineer</title></head><body>
<nav>Home | Careers | Login</nav>
<main><h1>Backend Engineer</h1>
<p>Example Corp is hiring a backend engineer to join our platform team in Munich. We build
software that helps thousands of small businesses run payroll every month.</p>
<h2>Requirements</h2><ul>
<li>3+ years of experience building backend services in Python or Go</li>
<li>Experience with PostgreSQL and Redis in production environments</li>
<li>Good understanding of REST API design and authentication</li>
</ul>
<h2>Nice to have</h2><ul><li>Experience with Kubernetes and Terraform</li></ul>
<p>Send your CV and tell us about a system you are proud of.</p></main>
<footer>Imprint | Privacy</footer></body></html>"""


def _transport(routes: dict[str, httpx.Response]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, resp in routes.items():
            if str(request.url).startswith(prefix):
                return resp
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_html_to_text_keeps_structure():
    text = html_to_text("<h2>Requirements</h2><ul><li>Python</li><li>SQL</li></ul><p>Thanks</p>")
    assert text == "## Requirements\n\n- Python\n- SQL\n\nThanks"
    # Greenhouse returns HTML-escaped content
    assert html_to_text("&lt;ul&gt;&lt;li&gt;Go&lt;/li&gt;&lt;/ul&gt;") == "- Go"


def test_greenhouse_uses_public_api():
    api = "https://boards-api.greenhouse.io/v1/boards/examplecorp/jobs/123"
    payload = {
        "title": "ML Engineer",
        "location": {"name": "Amsterdam"},
        "content": "&lt;h3&gt;What you bring&lt;/h3&gt;&lt;ul&gt;&lt;li&gt;5 years of PyTorch experience in production&lt;/li&gt;&lt;/ul&gt;"
        + "&lt;p&gt;We are a team of researchers and engineers working on forecasting.&lt;/p&gt;",
    }
    job = fetch_url(
        "https://boards.greenhouse.io/examplecorp/jobs/123",
        transport=_transport({api: httpx.Response(200, text=json.dumps(payload))}),
    )
    assert job.source == "greenhouse"
    assert job.title == "ML Engineer"
    assert job.location == "Amsterdam"
    assert "- 5 years of PyTorch experience in production" in job.text


def test_lever_uses_public_api():
    pid = "0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"
    payload = {
        "text": "Data Engineer",
        "categories": {"location": "Remote - EU"},
        "descriptionPlain": "We move data around for a living, at scale, for many happy customers.",
        "lists": [
            {"text": "Requirements", "content": "<li>Airflow</li><li>dbt and Snowflake</li>"}
        ],
        "additionalPlain": "",
    }
    job = fetch_url(
        f"https://jobs.lever.co/examplecorp/{pid}",
        transport=_transport(
            {
                f"https://api.lever.co/v0/postings/examplecorp/{pid}": httpx.Response(
                    200, json=payload
                )
            }
        ),
    )
    assert job.source == "lever"
    assert "## Requirements\n- Airflow\n- dbt and Snowflake" in job.text


def test_generic_page_extracts_main_content():
    url = "https://careers.example.com/jobs/backend"
    job = fetch_url(url, transport=_transport({url: httpx.Response(200, text=LONG_PAGE)}))
    assert job.source == "html"
    assert "PostgreSQL and Redis" in job.text
    assert "Login" not in job.text
    assert job.language == "en"


def test_linkedin_is_refused():
    with pytest.raises(FetchError, match="paste"):
        fetch_url("https://www.linkedin.com/jobs/view/123")


def test_blocked_page_asks_for_paste(monkeypatch):
    monkeypatch.setenv("USE_PLAYWRIGHT", "false")
    from jobfit.config import get_settings

    get_settings.cache_clear()
    url = "https://careers.example.com/blocked"
    with pytest.raises(FetchError, match="paste"):
        fetch_url(url, transport=_transport({url: httpx.Response(403)}))


def test_pasted_text_detects_german():
    job = from_pasted_text(
        "Wir suchen eine Backend-Entwicklerin mit mehrjähriger Erfahrung in Python und "
        "PostgreSQL. Gute Deutschkenntnisse sind erforderlich."
    )
    assert job.source == "pasted"
    assert job.language == "de"
