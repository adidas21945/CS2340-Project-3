"""Story #2: answer a natural language question about scams.

For now the answer is the top matching passages from the knowledge base.
Story #3 replaces this with an LLM answer written from the same passages.
"""
from ingestion.pipeline.store import get_store
from ingestion.pipeline.types import SearchHit

TOP_K = 3


def answer_question(question: str, store=None) -> list[SearchHit]:
    store = store or get_store()
    return store.search(question, k=TOP_K)
