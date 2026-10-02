# Sample profile (fictional)

**Mira Lindqvist does not exist.** This profile is used for the public demo, tests and evals, so no real resume is ever committed to the repo.

| File | What it is |
|---|---|
| `resume.md` | Source of the resume |
| `resume.pdf` | Generated from `resume.md` by `build_resume_pdf.py`. Ingestion uses this file, so the PDF parser is exercised |
| `profile.yaml` | Contact details for the exported .docx header |
| `projects/*.md` | Project write-ups |
| `github/*.md` | Snapshots of README files for her (fictional) GitHub repos, so the demo works offline. Real GitHub ingestion uses the GitHub API |

Note that the profile is deliberately *not* perfect: there is no production Kubernetes experience (only a learning repo). The fabrication eval relies on this, by planting claims like "5 years of Kubernetes in production".

Rebuild the PDF after editing the resume:

```bash
cd backend
uv run python ../sample_profile/build_resume_pdf.py
```
