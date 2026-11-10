# ScamSense

RAG chatbot that helps older adults and caregivers check whether a message is a scam
and what to do if they were scammed. Answers are grounded in FTC and FBI guidance.

CS 2340 Objects and Design, Project 3.

## Setup

Requires Python 3.10 or newer (`python3 --version`). On a Mac with an older default, use `python3.12 -m venv .venv`.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
```

## Build the knowledge base

```bash
python manage.py seed_sources      # add the starter FTC/FBI pages
python manage.py ingest            # scrape, clean, chunk, embed, store
python manage.py smoke_retrieval   # check known questions find the right page
```

- `python manage.py ingest --clear` wipes the knowledge base and rebuilds it.
- `python manage.py ingest --source 3 7` re-ingests specific sources.
- Upload PDFs at `/ingestion/upload/` (log in as staff first).
- Browse sources, documents, chunks and ingestion runs at `/admin/`.

The first ingest without an OpenAI key downloads a small local embedding model (about 80 MB).

## Ask a question (stories #2, #3, #4)

```bash
python manage.py runserver
```

Open http://localhost:8000/ and type a question, or paste a suspicious message.

- **Grounded answers (#3):** the top passages are retrieved, passages that are not relevant enough
  are dropped (`RELEVANCE_MAX_DISTANCE`), and the LLM (`OPENAI_CHAT_MODEL`, default `gpt-4o-mini`)
  answers from those numbered passages only. Every fact must cite a passage like `[1]`. Answers that
  cite nothing are rejected, and the model replies "couldn't find this" when the passages don't cover
  the question.
- **Sources (#4):** only the passages the answer actually cites are listed, with a link, publisher,
  section and date, plus a "Show the passage used" toggle. Each `[n]` in the answer links to its
  source. PDF sources link to the uploaded file.
- **No key or LLM error:** the page shows the matching passages and their sources instead.

| File | What it does |
|---|---|
| `chat/answer.py` | Retrieve, filter, generate, check citations, build sources |
| `chat/prompts.py` | System prompt and passage formatting (story #8 adds intent prompts here) |
| `chat/llm.py` | OpenAI wrapper; every failure becomes `LLMError` |

### Adding or removing the OpenAI key

`OPENAI_API_KEY` in `.env` turns on LLM answers **and** switches embeddings from the local model to
OpenAI's `text-embedding-3-small`. After adding or removing the key, rebuild the knowledge base:

```bash
python manage.py ingest --clear
```

`RELEVANCE_MAX_DISTANCE=0.70` was tuned for both embedding models: on-topic questions score about
0.31-0.61 with OpenAI and 0.40-0.58 with the local model; off-topic ones mostly score 0.78+.

## Tests

```bash
OPENAI_API_KEY= python manage.py test ingestion chat
```

Tests use an in-memory store. Blanking the key as above makes sure they never call the OpenAI API.
On Windows, put a `#` in front of `OPENAI_API_KEY` in `.env` while running the tests instead.

## How ingestion works (stories #6 and #7)

```
scrape_url()  ─┐
               ├─> RawDoc ─> clean_text() ─> dedupe ─> chunk_text() ─> vector store
load_pdf()    ─┘
```

| File | What it does |
|---|---|
| `ingestion/pipeline/loaders.py` | Two ingestion methods: web scraping (trafilatura) and PDF upload (PyMuPDF) |
| `ingestion/pipeline/cleaning.py` | Unicode cleanup, boilerplate removal, PDF header/footer removal, de-hyphenation, content hash |
| `ingestion/pipeline/chunking.py` | Heading-aware chunks (~500 tokens, 50 overlap), drops tiny fragments |
| `ingestion/pipeline/store.py` | Vector store wrapper (Chroma) |
| `ingestion/pipeline/ingest.py` | Runs the pipeline, dedupes, replaces changed pages, logs an `IngestionRun` |

## For other stories: the retrieval contract

```python
from ingestion.pipeline.store import get_store

hits = get_store().search("someone says my Medicare card is suspended", k=5)
for h in hits:
    h.text            # chunk text to put in the prompt (#3)
    h.title, h.url    # show as the source (#4)
    h.publisher       # "FTC" / "FBI"
    h.published_date  # ISO date or ""
    h.heading         # section heading, often names the scam type (C1)
    h.score           # cosine distance, lower = more similar
    h.chunk_id        # Chunk pk, for logging which chunks were used
```

Where other stories plug in:

- **#5 define/update the dataset:** add, edit or disable rows in the `Source` model, then run ingest.
- **#11 clear/reload:** call `clear_knowledge_base()` then `run_ingestion(Source.objects.filter(enabled=True), trigger="reload")`.
- **#10 / #12 monitoring and logs:** `IngestionRun` already logs each ingest. Add a matching model for queries.
- **#9 accuracy tests:** extend `ingestion/eval/smoke_questions.json`.

Some seed URLs are best guesses. Any that 404 show up in the ingest output and on the
Source's `last_error` in the admin. Fix the URL or disable the source.
