import numpy as np

from jobfit.retrieval.embeddings import HashEmbedder
from jobfit.retrieval.rerank import LexicalReranker
from jobfit.retrieval.search import HybridRetriever


def test_hash_embedder_is_deterministic_and_normalized():
    e = HashEmbedder()
    a, b = e.embed(["Python backend APIs", "Python backend APIs"])
    assert np.allclose(a, b)
    assert abs(np.linalg.norm(a) - 1.0) < 1e-5
    sim_close = float(e.embed(["built REST APIs in Python"])[0] @ a)
    sim_far = float(e.embed(["watercolor painting class"])[0] @ a)
    assert sim_close > sim_far


def test_lexical_reranker_prefers_matching_passage():
    scores = LexicalReranker().score(
        "Experience with Terraform", ["Deployed to AWS using Terraform.", "Wrote unit tests."]
    )
    assert scores[0] > scores[1]


def test_hybrid_search_finds_relevant_evidence(sample_profile):
    r = HybridRetriever()
    hits = r.search("Experience with RabbitMQ or other message queues", k=3)
    assert hits
    assert "RabbitMQ" in hits[0].chunk.text

    hits = r.search("German language skills", k=3)
    assert any("German (B2)" in h.chunk.text for h in hits)


def test_empty_profile_returns_nothing():
    assert HybridRetriever().search("Python") == []
