"""Turns text into vectors. Nothing else.

Kept separate from the API so that loading a machine learning model into memory
is not the API's problem, and so this can be restarted without taking chat down.
"""

import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

def _int(name, default):
    return int(os.getenv(name, default))


MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# checked against the model at startup rather than trusted. Swapping the model
# without changing this is the mistake worth catching early, because every stored
# vector would silently be the wrong shape
DIMENSIONS = _int("EMBEDDING_DIMENSIONS", 384)

# texts per forward pass. 32 filled the CPU here, 64 was not faster
ENCODE_BATCH_SIZE = _int("EMBEDDING_BATCH_SIZE", 32)

# a whole document in one request would hold it open with no progress reported
MAX_TEXTS = _int("EMBEDDING_MAX_TEXTS", 256)

state = {"model": None, "loaded_in": None}


@asynccontextmanager
async def lifespan(_app):
    started = time.monotonic()
    model = SentenceTransformer(MODEL_NAME, device="cpu")

    # embed something once here rather than letting the first real request pay
    # for the lazy setup inside the library
    check = model.encode("warm up", normalize_embeddings=True)
    if len(check) != DIMENSIONS:
        raise RuntimeError(f"{MODEL_NAME} returned {len(check)} dimensions, expected {DIMENSIONS}")

    state["model"] = model
    state["loaded_in"] = round(time.monotonic() - started, 1)
    yield
    state["model"] = None


app = FastAPI(title="ragops embeddings", lifespan=lifespan)


class EmbedRequest(BaseModel):
    # empty strings embed to something, and that something is meaningless.
    # Rejecting them here is cheaper than debugging a nonsense search result
    text: str = Field(min_length=1)


class EmbedResponse(BaseModel):
    embedding: list[float]


class BatchRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=MAX_TEXTS)


class BatchResponse(BaseModel):
    embeddings: list[list[float]]


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest):
    model = _model()
    vector = model.encode(request.text, normalize_embeddings=True)
    return {"embedding": vector.tolist()}


@app.post("/embed/batch", response_model=BatchResponse)
def embed_batch(request: BatchRequest):
    model = _model()

    if any(not text.strip() for text in request.texts):
        raise HTTPException(status_code=422, detail="one of the texts is empty")

    # one encode call, not one per text. The model batches internally and that
    # is where the time goes, not in the HTTP round trip
    vectors = model.encode(
        request.texts, normalize_embeddings=True, batch_size=ENCODE_BATCH_SIZE
    )
    return {"embeddings": [v.tolist() for v in vectors]}


def _model():
    if state["model"] is None:
        raise HTTPException(status_code=503, detail="model is still loading")
    return state["model"]


@app.get("/health")
def health():
    if state["model"] is None:
        raise HTTPException(status_code=503, detail="model is still loading")
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "dimensions": DIMENSIONS,
        "batch_size": ENCODE_BATCH_SIZE,
        "loaded_in": state["loaded_in"],
    }
