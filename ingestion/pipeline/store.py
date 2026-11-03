"""Vector store wrapper. The rest of the app only uses these four methods:

    store.add(records)            ingestion (#6)
    store.search(query, k)        retrieval (#3) and sources (#4)
    store.delete_document(doc_id) re-ingesting a changed page
    store.clear()                 admin clear/reload (#11)

Backed by Chroma (persistent, on disk). Swapping to pgvector later means
writing another class with the same four methods.

Embeddings:
- OPENAI_API_KEY set  -> OpenAI text-embedding-3-small
- otherwise           -> Chroma's local all-MiniLM-L6-v2 (no key, downloads once)
The model name is saved on the collection. If you switch models, run
`python manage.py ingest --clear` so old vectors are rebuilt.
"""
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from django.conf import settings

from .types import SearchHit


@dataclass
class VectorRecord:
    chunk_id: int
    document_id: int
    text: str  # what the user sees (the chunk)
    embed_text: str  # what gets embedded (title + heading + chunk)
    metadata: dict  # title, url, publisher, published_date, heading, source_type


def _hit(chunk_id, text, distance, meta) -> SearchHit:
    return SearchHit(
        text=text,
        score=float(distance),
        chunk_id=int(chunk_id),
        document_id=int(meta.get("document_id", 0)),
        title=meta.get("title", ""),
        url=meta.get("url", ""),
        publisher=meta.get("publisher", ""),
        published_date=meta.get("published_date", ""),
        heading=meta.get("heading", ""),
    )


class ChromaStore:
    def __init__(self, path: str, collection: str):
        import chromadb
        from chromadb.utils import embedding_functions as ef

        self._client = chromadb.PersistentClient(path=path)
        self._collection_name = collection
        if os.environ.get("OPENAI_API_KEY"):
            self.model_name = "openai/text-embedding-3-small"
            self._embed = ef.OpenAIEmbeddingFunction(
                api_key=os.environ["OPENAI_API_KEY"], model_name="text-embedding-3-small"
            )
        else:
            self.model_name = "local/all-MiniLM-L6-v2"
            self._embed = ef.DefaultEmbeddingFunction()
        self._col = self._get_collection()

    def _get_collection(self):
        col = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine", "embedding_model": self.model_name},
        )
        stored = (col.metadata or {}).get("embedding_model")
        if stored and stored != self.model_name and col.count() > 0:
            raise RuntimeError(
                f"Vector store was built with {stored} but current model is {self.model_name}. "
                "Run `python manage.py ingest --clear` to rebuild."
            )
        return col

    def add(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        self._col.upsert(
            ids=[str(r.chunk_id) for r in records],
            documents=[r.text for r in records],
            embeddings=self._embed([r.embed_text for r in records]),
            metadatas=[{**r.metadata, "document_id": r.document_id} for r in records],
        )

    def search(self, query: str, k: int = 5, where: Optional[dict] = None) -> list[SearchHit]:
        if self._col.count() == 0:
            return []
        res = self._col.query(
            query_embeddings=self._embed([query]),
            n_results=k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        return [
            _hit(cid, doc, dist, meta)
            for cid, doc, dist, meta in zip(
                res["ids"][0], res["documents"][0], res["distances"][0], res["metadatas"][0]
            )
        ]

    def delete_document(self, document_id: int) -> None:
        self._col.delete(where={"document_id": document_id})

    def clear(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._col = self._get_collection()

    def count(self) -> int:
        return self._col.count()


class InMemoryStore:
    """Bag-of-words store for unit tests. No embeddings, no disk, no network."""

    def __init__(self):
        self.model_name = "test/bag-of-words"
        self._records: dict[int, VectorRecord] = {}

    @staticmethod
    def _vec(text: str) -> Counter:
        return Counter(re.findall(r"[a-z0-9]+", text.lower()))

    @staticmethod
    def _cos_distance(a: Counter, b: Counter) -> float:
        dot = sum(a[t] * b[t] for t in a)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return 1.0 - (dot / (na * nb) if na and nb else 0.0)

    def add(self, records):
        for r in records:
            self._records[r.chunk_id] = r

    def search(self, query, k=5, where=None):
        q = self._vec(query)
        scored = sorted(
            (self._cos_distance(q, self._vec(r.embed_text)), r) for r in self._records.values()
        )
        return [
            _hit(r.chunk_id, r.text, d, {**r.metadata, "document_id": r.document_id})
            for d, r in scored[:k]
        ]

    def delete_document(self, document_id):
        self._records = {k: r for k, r in self._records.items() if r.document_id != document_id}

    def clear(self):
        self._records.clear()

    def count(self):
        return len(self._records)


@lru_cache(maxsize=1)
def get_store():
    if getattr(settings, "VECTOR_STORE_BACKEND", "chroma") == "memory":
        return InMemoryStore()
    return ChromaStore(path=str(settings.CHROMA_DIR), collection=settings.VECTOR_COLLECTION)
