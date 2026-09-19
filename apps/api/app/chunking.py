"""Split source text into retrieval-sized chunks.

Sized in characters rather than tokens: the encoder truncates at 512 tokens
(app/embeddings.py) and multilingual text has no stable characters-per-token
ratio, so the budget stays conservative enough for CJK input.
"""
import re

MAX_CHUNK_CHARS = 1000
CHUNK_OVERLAP_CHARS = 120

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?。！？])\s+|\n+")


def _hard_cut(text: str, max_chars: int, overlap: int) -> list[str]:
    """Cut text with no usable break (e.g. unspaced Chinese) into overlapping windows.

    The overlap keeps a match that straddles a cut inside at least one chunk.
    """
    pieces: list[str] = []
    start = 0
    while start < len(text):
        pieces.append(text[start : start + max_chars])
        if start + max_chars >= len(text):
            break
        start += max_chars - overlap
    return pieces


def _split_oversized(text: str, max_chars: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    for sentence in (part.strip() for part in _SENTENCE.split(text)):
        if not sentence:
            continue
        if pieces and len(pieces[-1]) + 1 + len(sentence) <= max_chars:
            pieces[-1] = f"{pieces[-1]}\n{sentence}"
        elif len(sentence) <= max_chars:
            pieces.append(sentence)
        else:
            pieces.extend(_hard_cut(sentence, max_chars, overlap))
    return pieces


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Return non-empty chunks of at most max_chars, preferring paragraph breaks."""
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")
    chunks: list[str] = []
    for paragraph in (part.strip() for part in _PARAGRAPH.split(text)):
        if not paragraph:
            continue
        if len(paragraph) > max_chars:
            chunks.extend(_split_oversized(paragraph, max_chars, overlap))
        elif chunks and len(chunks[-1]) + 2 + len(paragraph) <= max_chars:
            chunks[-1] = f"{chunks[-1]}\n\n{paragraph}"
        else:
            chunks.append(paragraph)
    return chunks
