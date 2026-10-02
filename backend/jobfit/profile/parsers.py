"""Convert resume files (PDF, DOCX, Markdown) to Markdown.

Everything downstream works on Markdown, so there is a single chunker no matter
which parser produced the text.

- PDF, default: PyMuPDF. Rebuilds headings and bullets from font sizes, bold flags and
  bullet characters. Fast, no model downloads.
- PDF, `RESUME_PARSER=docling`: Docling's layout model. Better for multi-column or
  unusual layouts, but needs `uv sync --extra docling`.
"""

from __future__ import annotations

import io
import os
import unicodedata
from collections import Counter
from pathlib import Path

BULLET_CHARS = "•●▪■◦‣∙·*–-"


def pdf_to_markdown(data: bytes) -> str:
    if os.environ.get("RESUME_PARSER", "").lower() == "docling":
        return _pdf_to_markdown_docling(data)
    return _pdf_to_markdown_pymupdf(data)


def _pdf_to_markdown_docling(data: bytes) -> str:
    try:
        from docling.datamodel.base_models import DocumentStream
        from docling.document_converter import DocumentConverter
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("RESUME_PARSER=docling needs `uv sync --extra docling`") from exc
    result = DocumentConverter().convert(DocumentStream(name="resume.pdf", stream=io.BytesIO(data)))
    return result.document.export_to_markdown()


def _pdf_to_markdown_pymupdf(data: bytes) -> str:
    import pymupdf

    lines: list[dict] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page_no, page in enumerate(doc):
            for block in page.get_text("dict", sort=True)["blocks"]:
                for line in block.get("lines", []):
                    spans = [s for s in line["spans"] if s["text"].strip()]
                    if not spans:
                        continue
                    lines.append(
                        {
                            # NFKC turns ligatures like "ﬂ" back into "fl", so keyword search works.
                            "text": unicodedata.normalize(
                                "NFKC", " ".join(s["text"].strip() for s in spans)
                            ),
                            "size": max(s["size"] for s in spans),
                            "bold": all(
                                s["flags"] & 16 or "bold" in s["font"].lower() for s in spans
                            ),
                            "x0": line["bbox"][0],
                            "y0": line["bbox"][1] + page_no * 10_000,
                            "y1": line["bbox"][3] + page_no * 10_000,
                        }
                    )
    if not lines:
        return ""

    # The body font size is the size covering the most characters.
    sizes: Counter[float] = Counter()
    for ln in lines:
        sizes[round(ln["size"], 1)] += len(ln["text"])
    body = sizes.most_common(1)[0][0]

    out: list[str] = []
    prev: dict | None = None
    prev_kind = ""
    for ln in lines:
        text = ln["text"].strip()
        is_bullet = text[0] in BULLET_CHARS and len(text) > 2 and text[1] in "  \t"
        if ln["size"] >= body * 1.5:
            kind, md = "h", f"# {text}"
        elif ln["size"] >= body * 1.2:
            kind, md = "h", f"## {text}"
        elif ln["bold"] and not is_bullet and len(text) < 140:
            kind, md = "h", f"### {text}"
        elif is_bullet:
            kind, md = "bullet", f"- {text[1:].strip()}"
        else:
            close = prev is not None and ln["y0"] - prev["y1"] < ln["size"] * 0.8
            if prev_kind in ("bullet", "para") and close:
                # A wrapped line continues the previous item. After a hyphen ("LLM-"), join
                # without a space so "LLM-powered" survives the line break.
                sep = "" if out[-1].endswith("-") else " "
                out[-1] = f"{out[-1]}{sep}{text}"
                prev = ln
                continue
            kind, md = "para", text
        if kind == "h" or (kind != prev_kind and out and out[-1]):
            out.append("")
        out.append(md)
        if kind == "h":
            out.append("")
        prev, prev_kind = ln, kind
    return "\n".join(out).strip() + "\n"


def docx_to_markdown(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    out: list[str] = []
    for p in document.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        style = (p.style.name or "").lower() if p.style is not None else ""
        if style.startswith("title"):
            out += ["", f"# {text}", ""]
        elif style.startswith("heading"):
            level = int(style.split()[-1]) if style.split()[-1].isdigit() else 2
            out += ["", f"{'#' * min(level + 1, 4)} {text}", ""]
        elif "list" in style or text[0] in BULLET_CHARS:
            out.append(f"- {text.lstrip(BULLET_CHARS).strip()}")
        else:
            out.append(text)
    return "\n".join(out).strip() + "\n"


def file_to_markdown(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return pdf_to_markdown(data)
    if suffix == ".docx":
        return docx_to_markdown(data)
    if suffix in (".md", ".markdown", ".txt"):
        return data.decode("utf-8", errors="replace")
    raise ValueError(f"Unsupported file type: {suffix} (use .pdf, .docx, .md or .txt)")
