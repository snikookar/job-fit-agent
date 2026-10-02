"""Fetch a job posting from a URL and return clean text.

Order of attempts:
1. Known applicant tracking systems with public JSON/XML APIs (Greenhouse, Lever, Personio).
   Structured data, no HTML guessing, and the API is the documented way to read postings.
2. Generic page: httpx + trafilatura (main-content extraction, keeps lists as Markdown).
3. If the page is rendered by JavaScript and (2) got almost nothing: Playwright, if installed.

LinkedIn is refused on purpose: scraping it violates its terms. Paste the text instead.
"""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from langdetect import DetectorFactory, LangDetectException, detect

from jobfit.config import get_settings

log = logging.getLogger(__name__)
DetectorFactory.seed = 0  # make language detection deterministic

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36 job-fit-agent"
)
MIN_USEFUL_CHARS = 400


class FetchError(Exception):
    pass


@dataclass
class FetchedJob:
    text: str
    source: str  # "pasted" | "greenhouse" | "lever" | "personio" | "html" | "playwright"
    url: str | None = None
    language: str = "unknown"
    title: str | None = None
    company: str | None = None
    location: str | None = None


# --- HTML -> Markdown-ish text (for HTML fragments returned by ATS APIs) ---------------


class _HTMLToText(HTMLParser):
    BLOCK = {"p", "div", "section", "br", "tr", "ul", "ol"}
    SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "head"}

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in ("h1", "h2", "h3", "h4", "h5"):
            self.out.append("\n\n## ")
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "p", "ul", "ol"):
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.out.append("\n")


def html_to_text(fragment: str) -> str:
    parser = _HTMLToText()
    parser.feed(html.unescape(fragment) if "&lt;" in fragment else fragment)
    return clean_text("".join(parser.out))


def clean_text(text: str) -> str:
    text = text.replace(" ", " ").replace("\r", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n- *\n", "\n", text)  # empty bullets
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_language(text: str) -> str:
    try:
        return detect(text[:5000])
    except LangDetectException:
        return "unknown"


# --- ATS adapters ----------------------------------------------------------------------


def _greenhouse(url: str, client: httpx.Client) -> FetchedJob | None:
    m = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)", url)
    if not m:
        return None
    board, job_id = m.groups()
    r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
    r.raise_for_status()
    data = r.json()
    body = html_to_text(data.get("content", ""))
    title = data.get("title")
    location = (data.get("location") or {}).get("name")
    text = f"# {title}\n\nLocation: {location}\n\n{body}" if location else f"# {title}\n\n{body}"
    return FetchedJob(text, "greenhouse", url, title=title, company=board, location=location)


def _lever(url: str, client: httpx.Client) -> FetchedJob | None:
    m = re.search(r"jobs\.(?:eu\.)?lever\.co/([\w-]+)/([0-9a-f-]{36})", url)
    if not m:
        return None
    company, posting_id = m.groups()
    api = "https://api.eu.lever.co" if ".eu.lever.co" in url else "https://api.lever.co"
    r = client.get(f"{api}/v0/postings/{company}/{posting_id}")
    r.raise_for_status()
    d = r.json()
    parts = [f"# {d.get('text', '')}"]
    cats = d.get("categories") or {}
    if cats.get("location"):
        parts.append(f"Location: {cats['location']}")
    parts.append(d.get("descriptionPlain") or html_to_text(d.get("description", "")))
    for lst in d.get("lists", []):
        parts.append(f"## {lst.get('text', '')}\n{html_to_text(lst.get('content', ''))}")
    parts.append(d.get("additionalPlain") or "")
    return FetchedJob(
        clean_text("\n\n".join(parts)),
        "lever",
        url,
        title=d.get("text"),
        company=company,
        location=cats.get("location"),
    )


def _personio(url: str, client: httpx.Client) -> FetchedJob | None:
    m = re.search(r"https?://([\w-]+)\.jobs\.personio\.(?:de|com)/job/(\d+)", url)
    if not m:
        return None
    company, job_id = m.groups()
    r = client.get(f"https://{company}.jobs.personio.de/xml")
    r.raise_for_status()
    root = ET.fromstring(r.content)
    for pos in root.iter("position"):
        if (pos.findtext("id") or "").strip() != job_id:
            continue
        title = (pos.findtext("name") or "").strip()
        office = (pos.findtext("office") or "").strip() or None
        parts = [f"# {title}"]
        if office:
            parts.append(f"Location: {office}")
        for desc in pos.iter("jobDescription"):
            parts.append(f"## {(desc.findtext('name') or '').strip()}")
            parts.append(html_to_text(desc.findtext("value") or ""))
        return FetchedJob(
            clean_text("\n\n".join(parts)), "personio", url, title=title, company=company, location=office
        )
    return None


# --- generic pages -------------------------------------------------------------------------


def _extract_main(page_html: str, url: str) -> str:
    import trafilatura

    text = trafilatura.extract(
        page_html,
        url=url,
        output_format="markdown",
        include_formatting=True,
        include_links=False,
        include_images=False,
        include_tables=True,
        favor_recall=True,
    )
    text = clean_text(text or "")
    if len(text) < MIN_USEFUL_CHARS:
        # trafilatura can drop content on very small pages; fall back to a plain conversion
        fallback = html_to_text(page_html)
        if len(fallback) > len(text):
            return fallback
    return text


def _playwright_html(url: str, timeout_s: float) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)
            return page.content()
        finally:
            browser.close()


def fetch_url(url: str, transport: httpx.BaseTransport | None = None) -> FetchedJob:
    s = get_settings()
    host = urlparse(url).netloc.lower()
    if not host:
        raise FetchError(f"Not a valid URL: {url}")
    if "linkedin." in host:
        raise FetchError(
            "LinkedIn pages are not fetched (scraping violates LinkedIn's terms). "
            "Please paste the job description text instead."
        )

    headers = {"User-Agent": USER_AGENT, "Accept-Language": "en,de;q=0.8"}
    with httpx.Client(
        timeout=s.fetch_timeout_s, follow_redirects=True, headers=headers, transport=transport
    ) as client:
        for adapter in (_greenhouse, _lever, _personio):
            try:
                job = adapter(url, client)
            except (httpx.HTTPError, ET.ParseError, ValueError) as exc:
                log.info("%s adapter failed for %s: %s", adapter.__name__, url, exc)
                job = None
            if job and len(job.text) > 100:
                job.language = detect_language(job.text)
                return job

        try:
            r = client.get(url)
            r.raise_for_status()
            text = _extract_main(r.text, url)
        except httpx.HTTPError as exc:
            text = ""
            log.info("plain fetch failed for %s: %s", url, exc)

    source = "html"
    if len(text) < MIN_USEFUL_CHARS and s.use_playwright:
        rendered = _playwright_html(url, s.fetch_timeout_s)
        if rendered:
            text, source = _extract_main(rendered, url), "playwright"

    if len(text) < 100:
        raise FetchError(
            "Could not extract the job description from this page (it may block bots or need "
            "JavaScript). Please paste the text instead."
        )
    return FetchedJob(text, source, url, language=detect_language(text))


def from_pasted_text(text: str) -> FetchedJob:
    text = clean_text(text)
    if len(text) < 50:
        raise FetchError("The job description is too short.")
    return FetchedJob(text, "pasted", language=detect_language(text))
