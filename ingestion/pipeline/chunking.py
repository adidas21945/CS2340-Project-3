"""Story #7 (part 2): split cleaned text into retrieval-sized chunks.

Strategy:
1. Split into sections on markdown headings (FTC headings usually name the scam
   type or the action, e.g. "What to do if you paid a scammer").
2. Pack paragraphs into chunks of up to MAX_TOKENS, with OVERLAP_TOKENS carried over.
3. Drop chunks smaller than MIN_TOKENS (leftover fragments retrieve badly).

Token counts are estimated (words / 0.75), which is close enough for sizing.
"""
import re

from .types import ChunkData

MAX_TOKENS = 500
OVERLAP_TOKENS = 50
MIN_TOKENS = 40

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def estimate_tokens(text: str) -> int:
    return int(len(text.split()) / 0.75)


def split_sections(text: str) -> list[tuple[str, str]]:
    """Return [(heading_path, body)] where heading_path is like "Gift card scams > What to do"."""
    sections: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    body: list[str] = []

    def flush():
        content = "\n".join(body).strip()
        if content:
            sections.append((" > ".join(h for _, h in stack), content))
        body.clear()

    for line in text.split("\n"):
        m = _HEADING.match(line.strip())
        if m:
            flush()
            level, title = len(m.group(1)), m.group(2).strip()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
        else:
            body.append(line)
    flush()
    return sections


def _split_long_paragraph(para: str, max_tokens: int) -> list[str]:
    if estimate_tokens(para) <= max_tokens:
        return [para]
    pieces, current = [], ""
    for sent in _SENTENCE_SPLIT.split(para):
        candidate = f"{current} {sent}".strip()
        if current and estimate_tokens(candidate) > max_tokens:
            pieces.append(current)
            current = sent
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def _tail(text: str, tokens: int) -> str:
    words = text.split()
    keep = int(tokens * 0.75)
    return " ".join(words[-keep:]) if keep else ""


def chunk_text(
    text: str,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
    min_tokens: int = MIN_TOKENS,
) -> list[ChunkData]:
    chunks: list[ChunkData] = []
    for heading, body in split_sections(text) or [("", text)]:
        paragraphs: list[str] = []
        for p in re.split(r"\n\s*\n", body):
            if p.strip():
                paragraphs.extend(_split_long_paragraph(p.strip(), max_tokens))

        current = ""
        for para in paragraphs:
            candidate = f"{current}\n\n{para}".strip()
            if current and estimate_tokens(candidate) > max_tokens:
                chunks.append(ChunkData(text=current, index=0, heading=heading))
                overlap = _tail(current, overlap_tokens)
                current = f"{overlap}\n\n{para}".strip() if overlap else para
            else:
                current = candidate
        if current:
            chunks.append(ChunkData(text=current, index=0, heading=heading))

    kept = []
    for c in chunks:
        c.token_count = estimate_tokens(c.text)
        if c.token_count >= min_tokens:
            c.index = len(kept)
            kept.append(c)
    return kept


def text_for_embedding(chunk: ChunkData, title: str) -> str:
    """Prefix title + heading so a chunk like "Don't pay with gift cards" still
    knows it belongs to "Gift card scams". Improves retrieval a lot for short chunks."""
    prefix = " > ".join(p for p in [title, chunk.heading] if p)
    return f"{prefix}\n\n{chunk.text}" if prefix else chunk.text
