"""Story #6: two distinct ingestion methods.

1. scrape_url(): web scraping of FTC / FBI IC3 pages (trafilatura pulls the main
   article and drops nav, footer and sidebars).
2. load_pdf(): direct file upload of PDF reports (PyMuPDF, page by page).

Both return a RawDoc. To add a third method (e.g. an API), write one more
function that returns a RawDoc and add a branch in ingest.load_source().
"""
from datetime import date, datetime
from typing import BinaryIO, Optional, Union

import pymupdf
import requests
import trafilatura

from .types import RawDoc

USER_AGENT = "ScamSenseBot/0.1 (Georgia Tech CS 2340 student project)"
TIMEOUT_SECONDS = 20


class LoaderError(Exception):
    pass


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%B %d, %Y"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            continue
    return None


def _publisher_from_url(url: str) -> str:
    if "ftc.gov" in url:
        return "FTC"
    if "ic3.gov" in url or "fbi.gov" in url:
        return "FBI"
    return ""


def fetch_html(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS)
    if resp.status_code != 200:
        raise LoaderError(f"GET {url} returned {resp.status_code}")
    return resp.text


def html_to_rawdoc(html: str, url: str = "", title: str = "", publisher: str = "") -> RawDoc:
    """Split out from scrape_url() so it can be tested with saved HTML, no network."""
    text = trafilatura.extract(
        html,
        url=url or None,
        output_format="markdown",
        include_tables=True,
        include_links=False,
        include_comments=False,
        favor_precision=True,
    )
    if not text:
        raise LoaderError(f"No main content found at {url or 'given HTML'}")
    meta = trafilatura.extract_metadata(html, default_url=url or None)
    return RawDoc(
        pages=[text],
        title=title or (meta.title if meta and meta.title else url),
        source_type="scrape",
        url=url,
        publisher=publisher or _publisher_from_url(url),
        published_date=_parse_date(meta.date if meta else None),
        has_markdown_headings=True,
    )


def scrape_url(url: str, title: str = "", publisher: str = "") -> RawDoc:
    return html_to_rawdoc(fetch_html(url), url=url, title=title, publisher=publisher)


def load_pdf(
    file: Union[str, BinaryIO, bytes],
    title: str = "",
    url: str = "",
    publisher: str = "",
    published_date: Optional[date] = None,
) -> RawDoc:
    try:
        if isinstance(file, (bytes, bytearray)):
            pdf = pymupdf.open(stream=file, filetype="pdf")
        elif isinstance(file, str):
            pdf = pymupdf.open(file)
        else:
            pdf = pymupdf.open(stream=file.read(), filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several types for bad files
        raise LoaderError(f"Could not open PDF: {exc}") from exc

    with pdf:
        pages = [page.get_text("text") for page in pdf]
        meta_title = (pdf.metadata or {}).get("title") or ""
    if not any(p.strip() for p in pages):
        raise LoaderError("PDF has no extractable text (scanned image? needs OCR)")
    return RawDoc(
        pages=pages,
        title=title or meta_title or "Untitled PDF",
        source_type="pdf",
        url=url,
        publisher=publisher,
        published_date=published_date,
    )
