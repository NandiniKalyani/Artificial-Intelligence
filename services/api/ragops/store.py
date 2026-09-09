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


def list_documents(qdrant=None, name=None):
    """Every document actually in the collection, with its chunk and page counts.

    Reads the payloads and counts in python. Qdrant has no group by, and at a few
    thousand points this is milliseconds. It stops being the right answer
    somewhere in the hundreds of thousands, and the fix then is to keep a
    document record rather than deriving it from the chunks.
    """
    qdrant = qdrant or client()
    name = name or config.COLLECTION

    documents = {}
    offset = None
    while True:
        points, offset = qdrant.scroll(
            collection_name=name,
            limit=1000,
            offset=offset,
            with_payload=["doc_id", "page"],
            with_vectors=False,
        )
        for point in points:
            doc_id = point.payload.get("doc_id", "unknown")
            record = documents.setdefault(doc_id, {"doc_id": doc_id, "chunks": 0, "pages": set()})
            record["chunks"] += 1
            if point.payload.get("page") is not None:
                record["pages"].add(point.payload["page"])
        if offset is None:
            break

    return sorted(
        (
            {
                "doc_id": r["doc_id"],
                "chunks": r["chunks"],
                "pages": len(r["pages"]),
                "first_page": min(r["pages"]) if r["pages"] else None,
                "last_page": max(r["pages"]) if r["pages"] else None,
            }
            for r in documents.values()
        ),
        key=lambda r: r["doc_id"],
    )


def get_chunks(doc_id, page=None, limit=20, offset=0, qdrant=None, name=None):
    """Chunks for one document, in order, optionally from one page.

    Ordered by the chunk index rather than by whatever qdrant returns, because
    reading two chunks out of order while debugging a bad retrieval is worse
    than useless.
    """
    qdrant = qdrant or client()
    name = name or config.COLLECTION

    must = [FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
    if page is not None:
        must.append(FieldCondition(key="page", match=MatchValue(value=page)))

    found = []
    scroll_offset = None
    while True:
        points, scroll_offset = qdrant.scroll(
            collection_name=name,
            scroll_filter=Filter(must=must),
            limit=1000,
            offset=scroll_offset,
            with_payload=True,
            with_vectors=False,
        )
        found.extend(points)
        if scroll_offset is None:
            break

    found.sort(key=lambda p: p.payload.get("chunk", 0))
    window = found[offset : offset + limit]

    return {
        "doc_id": doc_id,
        "total": len(found),
        "returned": len(window),
        "chunks": [
            {
                "chunk": p.payload.get("chunk"),
                "page": p.payload.get("page"),
                "words": len(p.payload.get("text", "").split()),
                "text": p.payload.get("text", ""),
            }
            for p in window
        ],
    }


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


def upsert_chunks(pieces, vectors, doc_id, qdrant=None, name=None):
    """Upsert chunks that carry their own page and chunk index."""
    qdrant = qdrant or client()
    name = name or config.COLLECTION

    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}:{piece['chunk']}")),
            vector=vector,
            payload={
                "doc_id": doc_id,
                "chunk": piece["chunk"],
                "page": piece["page"],
                "text": piece["text"],
            },
        )
        for piece, vector in zip(pieces, vectors)
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
        {
            "score": h.score,
            "text": h.payload["text"],
            "doc_id": h.payload["doc_id"],
            "page": h.payload.get("page"),
        }
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
