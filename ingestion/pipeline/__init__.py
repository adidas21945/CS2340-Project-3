"""Ingestion pipeline: loaders -> cleaning -> chunking -> store.

Public entry points:
    ingest.run_ingestion(sources)   ingest many Source rows, logs an IngestionRun
    ingest.ingest_rawdoc(raw)       ingest one already-loaded document
    ingest.clear_knowledge_base()   wipe documents + vectors (story #11)
    store.get_store().search(q, k)  retrieval (story #3)
"""
