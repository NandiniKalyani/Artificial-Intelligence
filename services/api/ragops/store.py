"""Qdrant collection setup.

    python -m ragops.store          show the collection, create it if missing
    python -m ragops.store --reset  drop it and start again
"""

import argparse
import sys
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from . import config


def client():
    return QdrantClient(url=config.QDRANT_URL, timeout=30)


def ensure_collection(qdrant=None, name=None):
    qdrant = qdrant or client()
    name = name or config.COLLECTION

    if qdrant.collection_exists(name):
        return False

    qdrant.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=config.VECTOR_SIZE, distance=Distance.COSINE),
    )

    # without this the doc_id filter does a full scan, which is fine at ten
    # documents and not at a thousand
    qdrant.create_payload_index(
        collection_name=name,
        field_name="doc_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    return True


def describe(qdrant=None, name=None):
    qdrant = qdrant or client()
    name = name or config.COLLECTION
    info = qdrant.get_collection(name)
    params = info.config.params.vectors
    return {
        "name": name,
        "points": info.points_count,
        "size": params.size,
        "distance": params.distance.name.lower(),
    }


def upsert(texts, vectors, doc_id, qdrant=None, name=None):
    """Store passages with their text kept alongside the vector.

    Qdrant does not give the text back on its own, only ids and scores, and a
    search result with no text in it is useless for debugging retrieval.
    """
    qdrant = qdrant or client()
    name = name or config.COLLECTION

    points = [
        PointStruct(
            # uuid5 off the doc id and position, so re-ingesting a document
            # overwrites its chunks instead of doubling them
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:{i}")),
            vector=vector,
            payload={"doc_id": doc_id, "chunk": i, "text": text},
        )
        for i, (text, vector) in enumerate(zip(texts, vectors))
    ]
    qdrant.upsert(collection_name=name, points=points, wait=True)
    return len(points)


def search(vector, limit=3, doc_id=None, qdrant=None, name=None):
    qdrant = qdrant or client()
    name = name or config.COLLECTION

    query_filter = None
    if doc_id:
        query_filter = Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        )

    hits = qdrant.query_points(
        collection_name=name,
        query=vector,
        limit=limit,
        query_filter=query_filter,
        with_payload=True,
    ).points

    return [
        {"score": h.score, "text": h.payload["text"], "doc_id": h.payload["doc_id"]}
        for h in hits
    ]


def main(argv=None):
    args = _parse(argv)
    qdrant = client()

    try:
        if args.reset and qdrant.collection_exists(config.COLLECTION):
            qdrant.delete_collection(config.COLLECTION)
            print(f"dropped {config.COLLECTION}")

        if ensure_collection(qdrant):
            print(f"created {config.COLLECTION}")

        for key, value in describe(qdrant).items():
            print(f"{key}: {value}")
    except Exception as exc:
        print(f"qdrant at {config.QDRANT_URL} is not answering: {exc}", file=sys.stderr)
        return 1
    return 0


def _parse(argv):
    parser = argparse.ArgumentParser(prog="ragops.store")
    parser.add_argument("--reset", action="store_true", help="drop the collection first")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
