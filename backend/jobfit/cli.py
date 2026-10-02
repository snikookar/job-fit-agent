"""Command line interface.

    uv run jobfit load-sample
    uv run jobfit ingest resume.pdf projects/*.md
    uv run jobfit ingest-github octocat
    uv run jobfit analyze --file posting.txt            # stops at human review
    uv run jobfit analyze --url https://... --approve   # approve as is and export .docx
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from jobfit.db.session import init_db


def _print_event(e) -> None:
    if e.type == "node":
        t = e.data.get("trace", {})
        extra = {k: v for k, v in e.data.items() if k != "trace"}
        print(f"  ✓ {e.node:<20} {t.get('seconds', 0):>6.2f}s  {json.dumps(extra, ensure_ascii=False)}")
    elif e.type == "interrupt":
        print("  ⏸ human_review: waiting for approval")
    elif e.type == "error":
        print(f"  ✗ {e.node or 'run'} failed: {e.data['message']}", file=sys.stderr)
    elif e.type == "done":
        print(f"  ■ done {json.dumps(e.data)}")


def _show_result(values: dict) -> None:
    score = values.get("score") or {}
    print(f"\nScore: {score.get('score')} / 100   (must-have coverage {score.get('must_coverage')})")
    for item in score.get("items", []):
        print(f"  [{item['importance']:4}] {item['strength']:.2f}  {item['text']}")
    if values.get("gaps"):
        print("\nGaps:")
        for g in values["gaps"]:
            print(f"  - ({g['importance']}) {g['text']}\n      → {g['suggestion']}")
    draft = values.get("final_draft") or values.get("draft") or {}
    print("\nBullets:")
    for s in draft.get("bullets", []):
        print(f"  • {s['text']}   [{', '.join(s['evidence_ids'])}]")
    print("\nCover letter:")
    for s in draft.get("cover_letter", []):
        print(f"  {s['text']}   [{', '.join(s['evidence_ids'])}]")
    if values.get("removed"):
        print("\nRemoved (unsupported):")
        for v in values["removed"]:
            print(f"  ✗ {v['text']}  — {v['reason']}")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="jobfit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("load-sample", help="load the fictional demo profile")
    p_ing = sub.add_parser("ingest", help="ingest a resume (.pdf/.docx/.md) and project .md files")
    p_ing.add_argument("resume")
    p_ing.add_argument("projects", nargs="*")
    p_gh = sub.add_parser("ingest-github", help="ingest READMEs of a GitHub user or owner/repo list")
    p_gh.add_argument("target")
    p_an = sub.add_parser("analyze", help="analyze a job posting")
    src = p_an.add_mutually_exclusive_group(required=True)
    src.add_argument("--url")
    src.add_argument("--file", type=Path)
    p_an.add_argument("--approve", action="store_true", help="approve the draft as is and export .docx")
    args = parser.parse_args(argv)

    init_db()
    from jobfit.profile import ingest

    if args.cmd == "load-sample":
        for r in ingest.load_sample_profile():
            print(f"{r.source}: {r.chunks} chunks")
    elif args.cmd == "ingest":
        r = ingest.ingest_resume(Path(args.resume).name, Path(args.resume).read_bytes())
        print(f"{r.source}: {r.chunks} chunks")
        for p in map(Path, args.projects):
            r = ingest.ingest_markdown(p.name, p.read_text(encoding="utf-8"))
            print(f"{r.source}: {r.chunks} chunks")
    elif args.cmd == "ingest-github":
        for r in ingest.ingest_github(args.target):
            print(f"{r.source}: {r.chunks} chunks")
    elif args.cmd == "analyze":
        from jobfit.graph.runner import JobFitAgent
        from jobfit.schemas import ReviewDecision

        agent = JobFitAgent()
        run_id = uuid.uuid4().hex[:12]
        text = args.file.read_text(encoding="utf-8") if args.file else None
        print(f"run {run_id}")
        events = list(agent.start(run_id, job_url=args.url, job_text=text))
        for e in events:
            _print_event(e)
        if any(e.type == "error" for e in events):
            return 1
        if args.approve:
            for e in agent.resume(run_id, ReviewDecision(approved=True)):
                _print_event(e)
        values = agent.state(run_id) or {}
        _show_result(values)
        if values.get("docx_path"):
            print(f"\nSaved: {values['docx_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
