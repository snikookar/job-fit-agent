"""Build eval/fabrication_set.jsonl: true sentences from the sample profile, and copies of
them with a deliberately planted fake claim.

    cd backend && uv run python ../eval/build_fabrication_set.py

Each line: {id, label: "fabricated" | "clean", mutation, section, text, evidence_ids, source_text}.
The output is committed, so every eval run uses the exact same cases.
"""

from __future__ import annotations

import json
import re

import _setup  # noqa: F401  (isolated DB; must come before jobfit imports)

from jobfit.profile.tech_tags import extract_tech_tags
from jobfit.retrieval import store
from jobfit.textutil import extract_numbers

N_FABRICATED = 100
N_CLEAN = 50
INJECTABLE_TOOLS = ["Kubernetes", "Kafka", "Spark", "Snowflake", "Rust", "Azure", "Elasticsearch", "MongoDB", "Redis", "GraphQL"]
PAST_VERB = re.compile(r"^(?:[A-Z][a-z]+ed|Built|Led|Ran|Wrote|Set)\b")


def _lower_first(s: str) -> str:
    return s[0].lower() + s[1:] if s else s


def _fresh_number(evidence: str, candidates=(7, 8, 12, 15, 35, 60, 250)) -> str:
    known = extract_numbers(evidence)
    return next(str(n) for n in candidates if str(n) not in known)


# --- mutations: (sentence, evidence_text) -> fabricated sentence or None ---------------------


def number_change(s: str, ev: str) -> str | None:
    # the first standalone number that isn't a year ("BM25" and "S3" are names, not claims)
    numbers = re.finditer(r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w])", s)
    m = next((m for m in numbers if not re.fullmatch(r"(19|20)\d\d", m.group(0))), None)
    if not m:
        return None
    digits = m.group(0).replace(",", "")
    try:
        new = str(int(float(digits) * 2 + 3)) if "." not in digits else f"{float(digits) * 2:.1f}"
    except ValueError:
        return None
    return s[: m.start()] + new + s[m.end() :]


def years_claim(s: str, ev: str) -> str:
    return f"{s.rstrip('.')}, drawing on {_fresh_number(ev)} years of experience in this area."


def tool_injection(s: str, ev: str) -> str:
    present = set(extract_tech_tags(ev))
    tool = next(t for t in INJECTABLE_TOOLS if t not in present)
    return f"{s.rstrip('.')}, using {tool}."


def scope_inflation(s: str, ev: str) -> str | None:
    if not PAST_VERB.match(s):
        return None
    return f"Led a team of engineers that {_lower_first(s)}"


def fake_certification(s: str, ev: str) -> str:
    return f"{s.rstrip('.')}, and earned the Google Professional Machine Learning Engineer certification."


def outcome_invention(s: str, ev: str) -> str:
    return f"{s.rstrip('.')}, which increased annual revenue by {_fresh_number(ev)}%."


def seniority(s: str, ev: str) -> str | None:
    if not PAST_VERB.match(s):
        return None
    return f"As the lead architect, I {_lower_first(s)}"


MUTATIONS = [number_change, years_claim, tool_injection, scope_inflation, fake_certification, outcome_invention, seniority]


def as_letter(s: str) -> str:
    return f"In my previous role, I {_lower_first(s)}" if PAST_VERB.match(s) else s


def base_sentences() -> list[tuple[str, str, str]]:
    """(sentence, chunk_id, evidence text) for single-claim profile sentences."""
    out = []
    for c in store.list_chunks():
        if c.source == "resume" and not c.section.startswith(("Experience", "Education")):
            continue  # skills lists and the header are not claims
        if c.section.endswith(("Overview", "Status")):
            continue  # descriptions of a repo, not achievements
        # Evidence includes the section name: "k8s-notes > Contents" implies Kubernetes.
        evidence = f"{c.section}: {c.text}"
        for line in c.text.splitlines():
            line = line.strip().lstrip("- ").strip()
            if len(line) >= 40 and not line.lower().startswith(("python,", "tests run")):
                out.append((line if line.endswith(".") else line + ".", c.id, evidence))
    return out


def main() -> None:
    _setup.load_profile()
    bases = base_sentences()
    cases = []

    # Learning-project trap: the profile says "I have not run Kubernetes in production".
    k8s = next(c for c in store.list_chunks() if "kind cluster" in c.text)
    cases.append(
        {
            "label": "fabricated",
            "mutation": "learning_to_production",
            "section": "bullets",
            "text": "Ran Kubernetes clusters in production for customer-facing FastAPI services.",
            "evidence_ids": [k8s.id],
            "source_text": k8s.text,
        }
    )

    i = 0
    while len(cases) < N_FABRICATED:
        sentence, cid, ev = bases[i % len(bases)]
        for shift in range(len(MUTATIONS)):  # if a mutation doesn't apply, try the next one
            mutate = MUTATIONS[(i + shift) % len(MUTATIONS)]
            fake = mutate(sentence, ev)
            if fake and fake != sentence:
                break
        section = "bullets" if i % 2 == 0 else "cover_letter"
        cases.append(
            {
                "label": "fabricated",
                "mutation": mutate.__name__,
                "section": section,
                "text": fake if section == "bullets" else as_letter(fake),
                "evidence_ids": [cid],
                "source_text": sentence,
            }
        )
        i += 1

    for j in range(N_CLEAN):
        sentence, cid, _ = bases[j % len(bases)]
        section = "bullets" if j % 2 == 0 else "cover_letter"
        cases.append(
            {
                "label": "clean",
                "mutation": None,
                "section": section,
                "text": sentence if section == "bullets" else as_letter(sentence),
                "evidence_ids": [cid],
                "source_text": sentence,
            }
        )

    path = _setup.EVAL_DIR / "fabrication_set.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for n, case in enumerate(cases):
            f.write(json.dumps({"id": f"case-{n:03d}", **case}, ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for c in cases:
        counts[c["mutation"] or "clean"] = counts.get(c["mutation"] or "clean", 0) + 1
    print(f"wrote {len(cases)} cases from {len(bases)} base sentences -> {path}")
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
