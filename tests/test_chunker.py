from __future__ import annotations

import pytest

from app.chunker import chunk_article_content, normalize_content


def test_chunk_article_content_uses_overlap() -> None:
    content = " ".join(f"word{index}" for index in range(12))
    chunks = chunk_article_content(content, chunk_words=5, overlap_words=2)

    assert [chunk["word_count"] for chunk in chunks] == [5, 5, 5, 3]
    assert chunks[0]["content"].split()[-2:] == chunks[1]["content"].split()[:2]
    assert len({chunk["content_hash"] for chunk in chunks}) == 1


def test_chunk_article_content_normalizes_whitespace() -> None:
    assert normalize_content("alpha\n\n beta\t gamma") == "alpha beta gamma"


def test_chunk_article_content_rejects_invalid_overlap() -> None:
    with pytest.raises(ValueError):
        chunk_article_content("some text", chunk_words=5, overlap_words=5)
