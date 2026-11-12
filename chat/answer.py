"""Stories #3, #4 and #8: an answer grounded in retrieved passages, plus the sources it used.

Flow:
0. Figure out the question type (scam check, recovery, how-to, factual) to pick teh prompt (#8).
1. Retrieve the top passages and drop any that are not relevant enough.
2. Ask the LLM to answer from those numbered passages only, citing them as [n].
3. Reject answers that cite nothing; renumber citations to match the sources shown.
4. If the LLM is unavailable (no key, network error), show the passages instead.
"""
import logging
import re
from dataclasses import dataclass, field

from django.conf import settings

from ingestion.models import Chunk
from ingestion.pipeline.store import get_store
from ingestion.pipeline.types import SearchHit

from .intents import Intent, classify_intent
from .llm import LLMError, generate
from .prompts import NOT_FOUND, build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)

TOP_K = 5
FALLBACK_SOURCES = 3
LLM, EXTRACTIVE, NO_MATCH = "llm", "extractive", "no_match"

EMPTY_KB_TEXT = "No information found yet. The knowledge base may be empty."
NO_MATCH_TEXT = (
    "I couldn't find this in the FTC and FBI guidance I have. If someone is pressuring you "
    "to pay or share information, stop and talk to someone you trust first."
)

_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


# one source we show under teh answer. number matches the [n] in the answer text
@dataclass
class SourceRef:
    number: int
    title: str
    url: str
    publisher: str
    published_date: str
    heading: str
    excerpt: str # the passage text, shows up when you click "Show the passage used"


# everything the ask page needs to show an answer adn its sources
@dataclass
class Answer:
    text: str
    mode: str  # LLM, EXTRACTIVE or NO_MATCH
    sources: list[SourceRef] = field(default_factory=list)
    hits: list[SearchHit] = field(default_factory=list)  # relevant passages retrieved
    intent: Intent = Intent.GENERAL # which question type picked the prompt (#8)


def renumber_citations(text: str, n_passages: int) -> tuple[str, list[int]]:
    """Keep valid [n] citations, renumber them 1..m by first use and drop invalid ones.

    Returns (new_text, original passage numbers in their new order).
    """
    order: list[int] = []
    for m in _CITATION.finditer(text):
        for n in (int(x) for x in m.group(1).split(",")):
            if 1 <= n <= n_passages and n not in order:
                order.append(n)
    mapping = {old: new for new, old in enumerate(order, 1)}

    def sub(m):
        nums = [int(x) for x in m.group(1).split(",")]
        return "".join(f"[{mapping[n]}]" for n in nums if n in mapping)

    return _CITATION.sub(sub, text), order


def _pdf_urls(hits: list[SearchHit]) -> dict[int, str]:
    """PDF chunks have no web URL, so link to the uploaded file instead."""
    ids = [h.chunk_id for h in hits if not h.url]
    if not ids:
        return {}
    rows = Chunk.objects.filter(pk__in=ids).select_related("document__source")
    return {
        c.pk: c.document.source.file.url
        for c in rows
        if c.document.source and c.document.source.file
    }


# turn the passages we used into numbered sources for the page (story #4)
# the order of hits has to match the [n] numbers in the answer, so source 1 is [1] and so on
# web pages link to their url, PDFs dont have one so they link to the uploaded file
def build_sources(hits: list[SearchHit]) -> list[SourceRef]:
    files = _pdf_urls(hits)
    return [
        SourceRef(
            number=i,
            title=h.title,
            url=h.url or files.get(h.chunk_id, ""), # fall back to the PDF file if theres no web url
            publisher=h.publisher,
            published_date=h.published_date,
            heading=h.heading,
            excerpt=h.text,
        )
        for i, h in enumerate(hits, 1)
    ]


# backup when we cant get a good LLM answer, jsut show the top few passages as is
# used when theres no key, the LLM call fails, or the answer didnt cite anything
def _extractive(hits: list[SearchHit]) -> Answer:
    top = hits[:FALLBACK_SOURCES]
    return Answer(text="", mode=EXTRACTIVE, sources=build_sources(top), hits=hits)


# main entry point for the ask page. figure out the intent, then get a grounded answer for it
# we set the intent after so every Answer has it, even the no match adn extractive ones
def answer_question(question: str, store=None) -> Answer:
    intent = classify_intent(question)
    logger.info("Question intent: %s", intent.value)
    answer = _grounded_answer(question, intent, store or get_store())
    answer.intent = intent
    return answer


# same flow as before #8, the only difference is the system prompt now depends on teh intent
def _grounded_answer(question: str, intent: Intent, store) -> Answer:
    # nothing came back at all, the knowledge base is probably empty
    results = store.search(question, k=TOP_K)
    if not results:
        return Answer(text=EMPTY_KB_TEXT, mode=NO_MATCH)

    # drop passages that arent close enough to the question to be useful
    hits = [h for h in results if h.score <= settings.RELEVANCE_MAX_DISTANCE]
    if not hits:
        return Answer(text=NO_MATCH_TEXT, mode=NO_MATCH)

    # ask the LLM with the prompt for this intent, if it fails show the passages instead
    try:
        reply = generate(build_system_prompt(intent), build_user_prompt(question, hits))
    except LLMError as exc:
        logger.warning("LLM unavailable, showing passages instead: %s", exc)
        return _extractive(hits)

    # the LLM said the passages dont cover this
    if NOT_FOUND in reply:
        return Answer(text=NO_MATCH_TEXT, mode=NO_MATCH, hits=hits)

    # only keep the passages it actually cited so the sources match the answer
    text, used = renumber_citations(reply, len(hits))
    if not used:  # an answer that cites nothing is not grounded
        logger.warning("LLM answer had no valid citations; showing passages instead")
        return _extractive(hits)
    cited = [hits[n - 1] for n in used]
    return Answer(text=text, mode=LLM, sources=build_sources(cited), hits=hits)
