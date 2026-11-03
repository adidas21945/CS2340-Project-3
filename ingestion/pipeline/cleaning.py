"""Story #7: clean and preprocess data before ingestion.

Pure functions only (no Django, no network) so they are easy to unit test.
"""
import hashlib
import re
import unicodedata
from collections import Counter

# Lines that show up on FTC / FBI pages but carry no scam guidance.
BOILERPLATE_PATTERNS = [
    r"^share this page$",
    r"^(facebook|twitter|x|linkedin|email|print)$",
    r"^search (consumer advice|this site)?$",
    r"^skip to (main )?content$",
    r"^an official website of the united states government$",
    r"^here'?s how you know$",
    r"^(back to top|read more|learn more)$",
    r"^related (articles|items|content)$",
    r"^(subscribe|sign up) (to|for) (consumer alerts|email updates).*$",
    r"^\|?\s*page \d+( of \d+)?\s*\|?$",
    r"^\d{1,4}$",  # bare page numbers
]
_BOILERPLATE_RE = [re.compile(p, re.IGNORECASE) for p in BOILERPLATE_PATTERNS]

_MULTI_SPACE = re.compile(r"[ \t ]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
# "fraud-\nulent" -> "fraudulent" (word broken across a line by the PDF layout)
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")


def normalize_unicode(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    # Curly quotes and dashes -> plain ASCII so search and dedupe behave.
    return (
        text.replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
        .replace("–", "-").replace("—", "-")
        .replace("­", "")  # soft hyphen
        .replace("\r\n", "\n").replace("\r", "\n")
    )


def is_boilerplate(line: str) -> bool:
    stripped = line.strip().strip("#").strip()
    if not stripped:
        return False
    return any(p.match(stripped) for p in _BOILERPLATE_RE)


_DIGITS = re.compile(r"\d+")
EDGE_LINES = 3  # headers/footers live in the first/last few lines of a page
MAX_HEADER_LEN = 80


def _edge_keys(page: str) -> dict[int, str]:
    """{line_number: key} for short lines near the top or bottom of a page.
    Digits are masked so "Page 3" and "Page 4" count as the same footer."""
    lines = page.split("\n")
    idx = [i for i, ln in enumerate(lines) if ln.strip()]
    n = max(1, min(EDGE_LINES, len(idx) // 3))  # short pages: only first/last line
    edge = set(idx[:n] + idx[-n:])
    return {
        i: _DIGITS.sub("#", lines[i].strip().lower())
        for i in edge
        if len(lines[i].strip()) <= MAX_HEADER_LEN
    }


def remove_repeated_lines(pages: list[str], min_share: float = 0.5) -> list[str]:
    """Drop running headers/footers: short lines at the top or bottom of most PDF pages.
    Body text is never touched, even if a sentence repeats across pages."""
    if len(pages) < 3:
        return pages
    edges = [_edge_keys(p) for p in pages]
    counts: Counter[str] = Counter()
    for e in edges:
        counts.update(set(e.values()))
    threshold = max(2, int(len(pages) * min_share))
    repeated = {k for k, c in counts.items() if c >= threshold}

    out = []
    for page, e in zip(pages, edges):
        lines = page.split("\n")
        drop = {i for i, key in e.items() if key in repeated}
        out.append("\n".join(ln for i, ln in enumerate(lines) if i not in drop))
    return out


def dehyphenate(text: str) -> str:
    return _HYPHEN_BREAK.sub(r"\1\2", text)


def rejoin_wrapped_lines(text: str) -> str:
    """PDFs hard-wrap every line. Join lines inside a paragraph, keep blank-line breaks,
    headings and list items."""
    out: list[str] = []
    for para in text.split("\n\n"):
        lines = [ln.strip() for ln in para.split("\n") if ln.strip()]
        merged: list[str] = []
        for ln in lines:
            starts_block = ln.startswith(("#", "-", "*", "•")) or re.match(r"^\d+[.)]\s", ln)
            if merged and not starts_block and not merged[-1].startswith("#"):
                merged[-1] = f"{merged[-1]} {ln}"
            else:
                merged.append(ln)
        out.append("\n".join(merged))
    return "\n\n".join(out)


def clean_text(pages: list[str], is_pdf: bool = False) -> str:
    pages = [normalize_unicode(p) for p in pages]
    if is_pdf:
        pages = remove_repeated_lines(pages)
    text = "\n\n".join(pages)
    if is_pdf:
        text = dehyphenate(text)
    lines = [ln for ln in text.split("\n") if not is_boilerplate(ln)]
    text = "\n".join(_MULTI_SPACE.sub(" ", ln).strip() for ln in lines)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    if is_pdf:
        text = rejoin_wrapped_lines(text)
    return text.strip()


def content_hash(text: str) -> str:
    """Hash of the cleaned text, whitespace- and case-insensitive. Used for dedupe."""
    canonical = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
