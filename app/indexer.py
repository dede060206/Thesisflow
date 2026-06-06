from __future__ import annotations

from app.chunker import chunk_article_content
from app.config import EMBEDDING_MODEL
from app.database import list_articles_for_indexing, replace_article_chunks
from app.embeddings import generate_embeddings


def index_article(article: dict) -> bool:
    chunks = chunk_article_content(article.get("content") or "")
    if not chunks:
        return False

    embedded = True
    try:
        embeddings = generate_embeddings([chunk["content"] for chunk in chunks])
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            chunk["embedding"] = embedding
    except Exception as exc:
        embedded = False
        print(f"Embedding failed for article {article['id']}: {exc}")

    replace_article_chunks(
        article_id=article["id"],
        chunks=chunks,
        embedding_model=EMBEDDING_MODEL if embedded else None,
    )
    return embedded


def index_pending_articles(limit: int = 100) -> dict[str, int]:
    articles = list_articles_for_indexing(limit=limit)
    indexed = 0
    embedded = 0
    for article in articles:
        if index_article(article):
            embedded += 1
        indexed += 1
    return {"found": len(articles), "indexed": indexed, "embedded": embedded}
