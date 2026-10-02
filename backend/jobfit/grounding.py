"""Grounding checks: is every sentence of a draft supported by the evidence it cites?

Three layers, cheapest first ("defense in depth"):

1. Citations (deterministic): the sentence cites at least one id, every id exists in the
   profile, and claims about the candidate don't cite only the job posting.
2. Numbers (deterministic): every number in the sentence ("5 years", "23%", "two") must
   appear in the cited evidence. Planted numbers are the most common fabrication, and
   this check catches them without trusting any model.
3. LLM judge: a *different* model than the writer reads each sentence with its evidence
   and decides supported / unsupported with a confidence. Catches inflated scope
   ("led" vs "contributed"), invented tools and paraphrased fabrications.

A sentence is supported only if it passes all three.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobfit.graph.prompts import render
from jobfit.llm.base import LLM
from jobfit.retrieval import store
from jobfit.schemas import JOB_EVIDENCE_ID, Chunk, Draft, DraftSentence, JudgeResult, Verdict
from jobfit.textutil import extract_numbers

SECTIONS = ("bullets", "cover_letter")
ALL_LAYERS = frozenset({"citations", "numbers", "llm"})


@dataclass
class _Item:
    section: str
    index: int
    sentence: DraftSentence
    evidence: list[tuple[str, str]]  # (id, text) of the cited evidence that exists
    failed: list[str]
    reasons: list[str]


def iter_sentences(draft: Draft):
    for section in SECTIONS:
        for i, s in enumerate(getattr(draft, section)):
            yield section, i, s


def _evidence_text(chunk: Chunk) -> str:
    parts = [chunk.text, f"(from: {chunk.section}"]
    if chunk.date_range:
        parts.append(f", dates: {chunk.date_range}")
    return "".join(parts) + ")"


def deterministic_checks(section: str, s: DraftSentence, chunks: dict[str, Chunk], job_text: str) -> _Item:
    failed: list[str] = []
    reasons: list[str] = []
    evidence: list[tuple[str, str]] = []

    ids = list(dict.fromkeys(s.evidence_ids))  # dedupe, keep order
    unknown = [i for i in ids if i != JOB_EVIDENCE_ID and i not in chunks]
    if not ids:
        failed.append("citations")
        reasons.append("cites no evidence")
    elif unknown:
        failed.append("citations")
        reasons.append(f"cites evidence that doesn't exist in the profile: {', '.join(unknown)}")
    if section == "bullets" and ids and all(i == JOB_EVIDENCE_ID for i in ids):
        failed.append("citations")
        reasons.append("a resume bullet must cite the profile, not the job posting")

    for i in ids:
        if i == JOB_EVIDENCE_ID:
            evidence.append((i, job_text))
        elif i in chunks:
            evidence.append((i, _evidence_text(chunks[i])))

    if evidence:
        known_numbers: set[str] = set()
        for _, text in evidence:
            known_numbers |= extract_numbers(text)
        missing = sorted(extract_numbers(s.text) - known_numbers)
        if missing:
            failed.append("numbers")
            reasons.append(f"number(s) not found in the cited evidence: {', '.join(missing)}")

    return _Item(section, -1, s, evidence, failed, reasons)


def _format_for_judge(items: list[_Item]) -> str:
    out = []
    for it in items:
        out.append(f"## {it.section} #{it.index}\nSentence: {it.sentence.text}\nCited evidence:")
        for eid, text in it.evidence:
            label = "job posting" if eid == JOB_EVIDENCE_ID else eid
            snippet = text if eid != JOB_EVIDENCE_ID else text[:3000]
            out.append(f"- [{label}] {snippet}")
        out.append("")
    return "\n".join(out)


def judge_draft(
    draft: Draft,
    job_text: str,
    judge: LLM,
    threshold: float = 0.5,
    cache: list[Verdict] | None = None,
    only: set[tuple[str, int]] | None = None,
    layers: frozenset[str] = ALL_LAYERS,
) -> list[Verdict]:
    """Return one Verdict per sentence (or per sentence in `only`).

    `cache`: verdicts from the previous round; a supported sentence that is unchanged
    (same text, same citations) is not sent to the LLM again.
    `layers`: which checks to run. Always all of them in the app; the eval switches layers
    off to measure what each one contributes.
    """
    all_ids = {i for _, _, s in iter_sentences(draft) for i in s.evidence_ids if i != JOB_EVIDENCE_ID}
    chunks = store.get_chunks(sorted(all_ids))
    cached = {
        (v.section, v.text, tuple(v.evidence_ids)): v for v in (cache or []) if v.supported
    }

    verdicts: dict[tuple[str, int], Verdict] = {}
    to_llm: list[_Item] = []
    for section, i, s in iter_sentences(draft):
        if only is not None and (section, i) not in only:
            continue
        key = (section, s.text, tuple(s.evidence_ids))
        if key in cached:
            verdicts[(section, i)] = cached[key].model_copy(update={"index": i})
            continue
        item = deterministic_checks(section, s, chunks, job_text)
        item.index = i
        failed = [(f, r) for f, r in zip(item.failed, item.reasons, strict=True) if f in layers]
        if failed:
            verdicts[(section, i)] = Verdict(
                section=section,
                index=i,
                text=s.text,
                evidence_ids=s.evidence_ids,
                supported=False,
                p_supported=0.0,
                reason="; ".join(r for _, r in failed),
                checks=[f for f, _ in failed],
            )
        elif "llm" in layers:
            to_llm.append(item)
        else:
            verdicts[(section, i)] = Verdict(
                section=section, index=i, text=s.text, evidence_ids=s.evidence_ids,
                supported=True, p_supported=1.0, reason="passed the enabled checks",
            )

    if to_llm:
        system, user = render("judge", sentences=_format_for_judge(to_llm))
        ctx = {
            "sentences": [
                {
                    "section": it.section,
                    "index": it.index,
                    "text": it.sentence.text,
                    "evidence": [{"id": eid, "text": text} for eid, text in it.evidence],
                }
                for it in to_llm
            ]
        }
        result = judge.structured("judge", system, user, JudgeResult, context=ctx)
        by_key = {(r.section, r.index): r for r in result.items}
        for it in to_llm:
            r = by_key.get((it.section, it.index))
            if r is None:  # the judge skipped it: be strict
                supported, p, reason = False, 0.0, "the judge returned no verdict for this sentence"
            else:
                p = r.confidence if r.supported else 1.0 - r.confidence
                supported, reason = p >= threshold, r.reason
            verdicts[(it.section, it.index)] = Verdict(
                section=it.section,
                index=it.index,
                text=it.sentence.text,
                evidence_ids=it.sentence.evidence_ids,
                supported=supported,
                p_supported=round(p, 3),
                reason=reason,
                checks=[] if supported else ["llm"],
            )

    return [verdicts[k] for k in sorted(verdicts, key=lambda k: (SECTIONS.index(k[0]), k[1]))]


def drop_unsupported(draft: Draft, verdicts: list[Verdict]) -> Draft:
    bad = {(v.section, v.index) for v in verdicts if not v.supported}
    return Draft(
        bullets=[s for i, s in enumerate(draft.bullets) if ("bullets", i) not in bad],
        cover_letter=[s for i, s in enumerate(draft.cover_letter) if ("cover_letter", i) not in bad],
    )
