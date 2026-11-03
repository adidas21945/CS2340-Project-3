"""Orchestration: RawDoc -> clean -> dedupe -> chunk -> store.

Every ingestion path (management command, PDF upload view, future admin reload
button) goes through ingest_rawdoc() / run_ingestion(), so behavior is identical.
"""
import logging
from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone

from ..models import Chunk, Document, IngestionRun, Source
from .chunking import chunk_text, text_for_embedding
from .cleaning import clean_text, content_hash
from .loaders import load_pdf, scrape_url
from .store import VectorRecord, get_store
from .types import RawDoc

logger = logging.getLogger(__name__)

MIN_DOCUMENT_CHARS = 300  # anything shorter is almost always a broken scrape

ADDED, UPDATED, SKIPPED = "added", "updated", "skipped"


def load_source(source: Source) -> RawDoc:
    if source.source_type == Source.SCRAPE:
        return scrape_url(source.url, title=source.name, publisher=source.publisher)
    if source.source_type == Source.PDF:
        if not source.file:
            raise ValueError(f"PDF source {source.pk} has no file")
        with source.file.open("rb") as fh:
            return load_pdf(
                fh,
                title=source.name,
                url=source.url,
                publisher=source.publisher,
                published_date=source.published_date,
            )
    raise ValueError(f"Unknown source type {source.source_type}")


def ingest_rawdoc(raw: RawDoc, source: Optional[Source] = None, store=None) -> tuple[str, int]:
    """Clean, dedupe, chunk and store one document. Returns (status, chunks_added)."""
    store = store or get_store()
    cleaned = clean_text(raw.pages, is_pdf=raw.source_type == Source.PDF)
    if len(cleaned) < MIN_DOCUMENT_CHARS:
        raise ValueError(f"'{raw.title}' has only {len(cleaned)} chars after cleaning")

    digest = content_hash(cleaned)
    if Document.objects.filter(content_hash=digest).exists():
        return SKIPPED, 0  # identical content already stored

    chunks = chunk_text(cleaned)
    if not chunks:
        raise ValueError(f"'{raw.title}' produced no chunks")

    # Same source or URL but new content: replace the old version.
    previous = Document.objects.none()
    if source is not None:
        previous = Document.objects.filter(source=source)
    elif raw.url:
        previous = Document.objects.filter(url=raw.url)
    status = UPDATED if previous.exists() else ADDED

    with transaction.atomic():
        for old in previous:
            store.delete_document(old.pk)
        previous.delete()

        doc = Document.objects.create(
            source=source,
            title=raw.title[:500],
            url=raw.url,
            publisher=raw.publisher,
            published_date=raw.published_date,
            source_type=raw.source_type,
            content_hash=digest,
            cleaned_text=cleaned,
            char_count=len(cleaned),
        )
        rows = Chunk.objects.bulk_create(
            Chunk(document=doc, index=c.index, heading=c.heading[:500], text=c.text, token_count=c.token_count)
            for c in chunks
        )
        meta = {
            "title": doc.title,
            "url": doc.url,
            "publisher": doc.publisher,
            "published_date": doc.published_date.isoformat() if doc.published_date else "",
            "source_type": doc.source_type,
        }
        # If the vector store fails, the transaction rolls back the DB rows too.
        store.add([
            VectorRecord(
                chunk_id=row.pk,
                document_id=doc.pk,
                text=c.text,
                embed_text=text_for_embedding(c, doc.title),
                metadata={**meta, "heading": c.heading},
            )
            for row, c in zip(rows, chunks)
        ])
    return status, len(chunks)


def run_ingestion(sources: Iterable[Source], trigger: str = "command", store=None) -> IngestionRun:
    """Ingest many sources. One bad source is logged and skipped, never fatal."""
    run = IngestionRun.objects.create(trigger=trigger)
    errors = []
    for source in sources:
        run.sources_processed += 1
        try:
            status, n_chunks = ingest_rawdoc(load_source(source), source=source, store=store)
            if status == ADDED:
                run.docs_added += 1
            elif status == UPDATED:
                run.docs_updated += 1
            else:
                run.docs_skipped += 1
            run.chunks_added += n_chunks
            source.last_error = ""
        except Exception as exc:  # keep going; record what failed
            logger.warning("Ingestion failed for %s: %s", source, exc)
            errors.append({"source_id": source.pk, "source": str(source), "error": str(exc)})
            source.last_error = str(exc)[:2000]
        source.last_ingested_at = timezone.now()
        source.save(update_fields=["last_ingested_at", "last_error"])

    run.errors = errors
    run.finished_at = timezone.now()
    if not errors:
        run.status = IngestionRun.SUCCESS
    elif len(errors) < run.sources_processed:
        run.status = IngestionRun.PARTIAL
    else:
        run.status = IngestionRun.FAILED
    run.save()
    return run


def clear_knowledge_base(store=None) -> None:
    """Wipe vectors and documents. Sources stay, so a reload rebuilds everything."""
    store = store or get_store()
    store.clear()
    Document.objects.all().delete()
