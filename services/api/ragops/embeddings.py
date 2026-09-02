"""Client for the embeddings service."""

import httpx

from . import config


class EmbeddingsError(RuntimeError):
    pass


def embed(text, url=None):
    return _post("/embed", {"text": text}, url)["embedding"]


def embed_batch(texts, url=None):
    return _post("/embed/batch", {"texts": list(texts)}, url)["embeddings"]


def _post(path, body, url=None):
    base = (url or config.EMBEDDINGS_URL).rstrip("/")
    try:
        response = httpx.post(f"{base}{path}", json=body, timeout=120)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EmbeddingsError(f"embeddings service at {base} failed: {exc}") from exc
    return response.json()
