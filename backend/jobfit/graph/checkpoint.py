"""LangGraph checkpointers: Postgres when DATABASE_URL is Postgres, SQLite otherwise.

The checkpointer stores the graph state after every node. That is what makes
`interrupt()` usable for human review: the run pauses, the process can even restart,
and `Command(resume=...)` continues from the saved state.
"""

from __future__ import annotations

import sqlite3

from langgraph.checkpoint.base import BaseCheckpointSaver

from jobfit.config import get_settings


def make_checkpointer() -> BaseCheckpointSaver:
    s = get_settings()
    if s.is_postgres:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        # PostgresSaver wants a plain libpq URL, not SQLAlchemy's "postgresql+psycopg://".
        url = s.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        conn = Connection.connect(url, autocommit=True, prepare_threshold=0, row_factory=dict_row)
        saver = PostgresSaver(conn)
        saver.setup()
        return saver

    from langgraph.checkpoint.sqlite import SqliteSaver

    s.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(s.checkpoint_db), check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver
