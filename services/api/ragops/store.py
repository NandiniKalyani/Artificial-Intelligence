"""Qdrant collection setup.

    python -m ragops.store          show the collection, create it if missing
    python -m ragops.store --reset  drop it and start again
"""

import argparse
import sys

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

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
