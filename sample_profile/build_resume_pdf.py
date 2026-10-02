"""Render sample_profile/resume.md to resume.pdf with PyMuPDF's HTML layout engine (Story).

Only the Markdown features used in resume.md are supported: #/##/### headings,
"- " bullets and plain paragraphs.
"""

import html
from pathlib import Path

import pymupdf

HERE = Path(__file__).resolve().parent

CSS = """
body { font-family: sans-serif; font-size: 10pt; line-height: 1.35; }
h1 { font-size: 20pt; margin: 0 0 2pt 0; }
h2 { font-size: 13pt; margin: 12pt 0 4pt 0; color: #1f3a5f; }
h3 { font-size: 11pt; margin: 8pt 0 0 0; font-weight: bold; }
p { margin: 2pt 0 4pt 0; }
ul { margin: 2pt 0 4pt 0; }
li { margin: 0 0 2pt 0; }
"""


def md_to_html(md: str) -> str:
    out: list[str] = []
    in_list = False
    for raw in md.splitlines():
        line = raw.strip()
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if not line:
            continue
        level = len(line) - len(line.lstrip("#"))
        if level and line[level:level + 1] == " ":
            out.append(f"<h{level}>{html.escape(line[level + 1:])}</h{level}>")
        else:
            out.append(f"<p>{html.escape(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def main() -> None:
    body = md_to_html((HERE / "resume.md").read_text(encoding="utf-8"))
    story = pymupdf.Story(html=body, user_css=CSS)
    writer = pymupdf.DocumentWriter(str(HERE / "resume.pdf"))
    page_rect = pymupdf.paper_rect("a4")
    content_rect = page_rect + (50, 50, -50, -50)
    more = True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
    writer.close()
    print(f"wrote {HERE / 'resume.pdf'}")


if __name__ == "__main__":
    main()
