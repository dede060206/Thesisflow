from __future__ import annotations

from openai import OpenAI

from app.config import EMBEDDING_DIMENSIONS, EMBEDDING_MODEL, OPENAI_API_KEY


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required to generate embeddings.")

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]
