"""Shared setup for eval scripts: an isolated database with the sample profile loaded.

Must be imported before anything from `jobfit`, because settings are read from the
environment on first use. Your real profile database is never touched.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
_tmp = Path(tempfile.mkdtemp(prefix="jobfit-eval-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'eval.db').as_posix()}"
os.environ["CHECKPOINT_DB"] = str(_tmp / "checkpoints.db")
os.environ["EXPORT_DIR"] = str(_tmp / "exports")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def load_profile() -> None:
    from jobfit.db.session import init_db
    from jobfit.profile.ingest import load_sample_profile

    init_db()
    load_sample_profile()
