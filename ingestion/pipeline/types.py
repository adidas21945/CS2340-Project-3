"""Shared data shapes for the ingestion pipeline.

Every loader (web scraping, PDF upload, anything added later) returns a RawDoc.
Everything downstream (cleaning, chunking, storage) only ever sees RawDoc and
ChunkData, so adding a new ingestion method means writing one new loader.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class RawDoc:
    # One string per page. HTML pages are a single "page".
    # PDFs keep their pages separate so the cleaner can spot repeated headers/footers.
    pages: list[str]
    title: str
    source_type: str  # "scrape" or "pdf"
    url: str = ""
    publisher: str = ""
    published_date: Optional[date] = None
    # True when the text is markdown with "#" headings (trafilatura output).
    has_markdown_headings: bool = False


@dataclass
class ChunkData:
    text: str
    index: int
    heading: str = ""
    token_count: int = 0


@dataclass
class SearchHit:
    """What VectorStore.search() returns. This is the contract for story #3 and #4."""
    text: str
    score: float  # cosine distance: lower = more similar
    chunk_id: int
    document_id: int
    title: str
    url: str
    publisher: str
    published_date: str  # ISO date or ""
    heading: str = ""
    extra: dict = field(default_factory=dict)
