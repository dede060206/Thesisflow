from __future__ import annotations

import hashlib
import re

from app.config import ARTICLE_CHUNK_OVERLAP_WORDS, ARTICLE_CHUNK_WORDS


def normalize_content(content: str) -> str:
    return re.sub(r"\s+", " ", content).strip()


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def chunk_article_content(
    content: str,
    chunk_words: int = ARTICLE_CHUNK_WORDS,
    overlap_words: int = ARTICLE_CHUNK_OVERLAP_WORDS,
) -> list[dict]:
    normalized = normalize_content(content)
    words = normalized.split()
    if not words:
        return []
    if chunk_words <= 0:
        raise ValueError("chunk_words must be positive")
    if overlap_words < 0 or overlap_words >= chunk_words:
        raise ValueError("overlap_words must be between 0 and chunk_words - 1")

    digest = content_hash(normalized)
    step = chunk_words - overlap_words
    chunks: list[dict] = []
    for index, start in enumerate(range(0, len(words), step)):
        chunk_words_list = words[start : start + chunk_words]
        if not chunk_words_list:
            break
        chunks.append(
            {
                "chunk_index": index,
                "content": " ".join(chunk_words_list),
                "word_count": len(chunk_words_list),
                "content_hash": digest,
            }
        )
        if start + chunk_words >= len(words):
            break
    return chunks
