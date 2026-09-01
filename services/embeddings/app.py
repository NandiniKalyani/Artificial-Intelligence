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

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
DIMENSIONS = 384

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


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest):
    model = state["model"]
    if model is None:
        raise HTTPException(status_code=503, detail="model is still loading")

    vector = model.encode(request.text, normalize_embeddings=True)
    return {"embedding": vector.tolist()}


@app.get("/health")
def health():
    if state["model"] is None:
        raise HTTPException(status_code=503, detail="model is still loading")
    return {"status": "ok", "model": MODEL_NAME, "dimensions": DIMENSIONS, "loaded_in": state["loaded_in"]}
