import numpy as np

from jobfit.db.models import Application, ChunkRow
from jobfit.db.session import session_scope


def test_chunk_embedding_roundtrip():
    vec = np.linspace(0, 1, 1024, dtype=np.float32)
    with session_scope() as s:
        s.add(ChunkRow(id="resume:001", source="resume", section="Experience", text="Built X", embedding=vec))
    with session_scope() as s:
        row = s.get(ChunkRow, "resume:001")
        assert row is not None
        assert isinstance(row.embedding, np.ndarray)
        assert np.allclose(row.embedding, vec)
        assert row.tech_tags == []


def test_application_defaults():
    with session_scope() as s:
        s.add(Application(title="AI Engineer", company="Example"))
    with session_scope() as s:
        app = s.query(Application).one()
        assert app.status == "saved"
        assert app.created_at is not None
