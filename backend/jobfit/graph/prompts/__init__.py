"""Prompt templates live in .md files next to this module.

Each file has a system part and a user part separated by a line `=== USER ===`.
Placeholders use `$name` (string.Template), so JSON braces in prompts need no escaping.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).parent
SEPARATOR = "=== USER ==="


@lru_cache
def _load(name: str) -> tuple[Template, Template]:
    raw = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    system, user = raw.split(SEPARATOR, 1)
    return Template(system.strip()), Template(user.strip())


def render(name: str, **values: object) -> tuple[str, str]:
    """Return (system, user) prompts with placeholders filled in."""
    system, user = _load(name)
    vals = {k: str(v) for k, v in values.items()}
    return system.substitute(vals), user.substitute(vals)
