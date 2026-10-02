from jobfit.profile.chunking import chunk_resume, chunk_sections, find_date_range
from jobfit.profile.parsers import pdf_to_markdown
from jobfit.profile.tech_tags import extract_tech_tags
from jobfit.retrieval import store


def test_pdf_to_markdown_recovers_structure(sample_profile_dir):
    md = pdf_to_markdown((sample_profile_dir / "resume.pdf").read_bytes())
    assert md.startswith("# Mira Lindqvist")
    assert "## Experience" in md
    assert "### Senior Backend Engineer — Quillbyte Analytics GmbH, Berlin" in md
    # wrapped bullet lines are merged back into one bullet
    assert "- Built a retrieval-augmented generation (RAG) assistant over 40,000" in md
    assert "cutting average ticket handling time by 23%." in md
    assert "LLM-powered" in md  # hyphen at a line break is kept without a space


def test_resume_chunks_are_bullets_with_dates():
    md = """# Jane Doe

## Experience

### Data Engineer — Acme, Berlin

01/2020 – present

- Built Kafka pipelines processing 2 TB per day.
- Ran the on-call rotation.

## Skills

- Python, SQL, Kafka
"""
    chunks = chunk_resume(md)
    assert [c.text for c in chunks] == [
        "Built Kafka pipelines processing 2 TB per day.",
        "Ran the on-call rotation.",
        "Python, SQL, Kafka",
    ]
    assert chunks[0].section == "Experience > Data Engineer — Acme, Berlin"
    assert chunks[0].date_range == "01/2020 – present"
    assert "Kafka" in chunks[0].tech_tags
    assert chunks[2].date_range is None
    assert chunks[0].id == "resume:000"


def test_readme_chunks_are_sections_without_code_or_badges():
    md = """# my-lib

![badge](https://x/y.svg)

A tiny library for caching.

## Install

```bash
pip install my-lib
```

## Features

- Fast
- Works with Redis and PostgreSQL
"""
    chunks = chunk_sections(md, "github:me/my-lib")
    sections = [c.section for c in chunks]
    assert sections == ["my-lib > Overview", "my-lib > Features"]  # Install had only code
    assert "badge" not in chunks[0].text
    assert chunks[1].tech_tags == ["PostgreSQL", "Redis"]


def test_date_range_formats():
    assert find_date_range("Mar 2021 - Present") == "Mar 2021 - Present"
    assert find_date_range("2016 – 2018") == "2016 – 2018"
    assert find_date_range("10.2019 bis heute") == "10.2019 bis heute"
    assert find_date_range("no dates here") is None


def test_tech_tags_avoid_false_positives():
    assert extract_tech_tags("Let's go to the office and rest") == []
    assert "Go" in extract_tech_tags("Backend services in Go and Rust")
    assert set(extract_tech_tags("k8s and C++ and node.js")) == {"Node.js", "C++", "Kubernetes"}


def test_sample_profile_ingestion(sample_profile):
    sources = {r.source: r.chunks for r in sample_profile}
    assert sources["resume"] > 15
    assert "github:mira-lindqvist-demo/pg-semantic-cache" in sources
    chunks = store.list_chunks("resume")
    assert any("pgvector" in c.text for c in chunks)
    # re-ingesting replaces instead of duplicating
    from jobfit.profile.ingest import load_sample_profile

    load_sample_profile()
    assert len(store.list_chunks("resume")) == len(chunks)
