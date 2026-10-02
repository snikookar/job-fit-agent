"""Split Markdown into profile chunks.

- Resumes: one chunk per bullet (or short paragraph). A bullet is one claim, which is
  exactly the unit the grounding judge needs to cite.
- READMEs and project write-ups: one chunk per section.

Each chunk keeps its heading path (`section`), a `date_range` taken from the nearest
role/education entry, and `tech_tags`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from jobfit.profile.tech_tags import extract_tech_tags
from jobfit.schemas import Chunk

_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_POINT = rf"(?:(?:\d{{1,2}}[/.])?\d{{4}}|{_MONTH}\s+\d{{4}})"
_END = rf"(?:{_POINT}|present|current|now|today|heute|aktuell)"
DATE_RANGE_RE = re.compile(rf"{_POINT}\s*(?:–|—|-|to|bis)\s*{_END}", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

MAX_SECTION_CHARS = 1500


def find_date_range(text: str) -> str | None:
    m = DATE_RANGE_RE.search(text)
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip()
    return None


@dataclass
class _Block:
    kind: str  # "heading" | "bullet" | "para"
    text: str
    level: int = 0


@dataclass
class _Section:
    path: list[str]
    lines: list[str] = field(default_factory=list)


def _clean_markdown(md: str) -> str:
    """Drop code blocks, images/badges and HTML noise that carry no evidence."""
    md = re.sub(r"```.*?```", "", md, flags=re.DOTALL)
    out = []
    for line in md.splitlines():
        s = line.strip()
        if s.startswith(("![", "[![", "<img", "<p align", "</p", "<a ", "<br", "<!--")):
            continue
        s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)  # inline images
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)  # links -> link text
        s = re.sub(r"[*_`]{1,3}([^*_`]+)[*_`]{1,3}", r"\1", s)  # emphasis / inline code
        out.append(s)
    return "\n".join(out)


def _blocks(md: str) -> list[_Block]:
    blocks: list[_Block] = []
    para: list[str] = []

    def flush() -> None:
        if para:
            blocks.append(_Block("para", " ".join(para)))
            para.clear()

    for line in _clean_markdown(md).splitlines():
        s = line.strip()
        heading = re.match(r"^(#{1,6})\s+(.*)$", s)
        bullet = re.match(r"^(?:[-*+•]|\d+[.)])\s+(.*)$", s)
        if not s:
            flush()
        elif heading:
            flush()
            blocks.append(_Block("heading", heading.group(2).strip(), len(heading.group(1))))
        elif bullet:
            flush()
            blocks.append(_Block("bullet", bullet.group(1).strip()))
        elif blocks and blocks[-1].kind == "bullet" and not para and line.startswith((" ", "\t")):
            blocks[-1].text += " " + s  # indented continuation of a bullet
        else:
            para.append(s)
    flush()
    return blocks


def _make_chunk(source: str, idx: int, section: str, text: str, date_range: str | None) -> Chunk:
    return Chunk(
        id=f"{source}:{idx:03d}",
        source=source,
        section=section or "General",
        text=text.strip(),
        date_range=date_range,
        tech_tags=extract_tech_tags(f"{section} {text}"),
    )


def chunk_resume(md: str, source: str = "resume") -> list[Chunk]:
    blocks = _blocks(md)
    chunks: list[Chunk] = []
    path: dict[int, str] = {}
    date_range: str | None = None
    pending_date = False  # the line right after an entry heading may hold its dates

    for b in blocks:
        if b.kind == "heading":
            path = {lvl: t for lvl, t in path.items() if lvl < b.level}
            path[b.level] = b.text
            date_range = find_date_range(b.text) if b.level >= 3 else None
            pending_date = b.level >= 3 and date_range is None
            continue

        # Section path without the document title (the person's name).
        levels = sorted(path)
        section_parts = [path[lvl] for lvl in levels if lvl > 1] if len(levels) > 1 else []
        section = " > ".join(section_parts) or ("Header" if levels else "General")

        if pending_date and b.kind == "para" and len(b.text) < 60:
            found = find_date_range(b.text) or (b.text if YEAR_RE.search(b.text) else None)
            pending_date = False
            if found:
                date_range = found
                continue
        pending_date = False

        if len(b.text) < 15:
            continue
        chunks.append(_make_chunk(source, len(chunks), section, b.text, date_range))
    return chunks


def chunk_sections(md: str, source: str) -> list[Chunk]:
    """README / project chunking: one chunk per section, long sections split by paragraph."""
    sections: list[_Section] = []
    path: dict[int, str] = {}
    current = _Section(path=[])
    for b in _blocks(md):
        if b.kind == "heading":
            if current.lines:
                sections.append(current)
            path = {lvl: t for lvl, t in path.items() if lvl < b.level}
            path[b.level] = b.text
            current = _Section(path=[path[lvl] for lvl in sorted(path)])
        else:
            current.lines.append(f"- {b.text}" if b.kind == "bullet" else b.text)
    if current.lines:
        sections.append(current)

    whole_doc = md
    doc_dates = find_date_range(whole_doc) or (
        m.group(0) if (m := YEAR_RE.search(whole_doc[:400])) else None
    )

    chunks: list[Chunk] = []
    for sec in sections:
        title = sec.path[0] if sec.path else ""
        sub = " > ".join(sec.path[1:]) or "Overview"
        section_name = f"{title} > {sub}" if title else sub
        for part in _split_long(sec.lines):
            if len(part) < 20:
                continue
            chunks.append(_make_chunk(source, len(chunks), section_name, part, doc_dates))
    return chunks


def _split_long(lines: list[str]) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    for line in lines:
        if buf and sum(len(x) for x in buf) + len(line) > MAX_SECTION_CHARS:
            parts.append("\n".join(buf))
            buf = []
        buf.append(line)
    if buf:
        parts.append("\n".join(buf))
    return parts
