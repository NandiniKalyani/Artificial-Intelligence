"""Take a PDF from a file on disk to something searchable.

    python -m ragops.ingest data/sharepoint.pdf
    python -m ragops.ingest data/sharepoint.pdf --limit 200 --doc-id trial

Streams. Pages come out one at a time, chunks are batched, and each batch is
embedded and upserted before the next is read. Nothing holds the document.
"""

import argparse
import sys
import time
from itertools import islice
from pathlib import Path

from . import chunk, config, embeddings, pdf, store


def ingest(path, doc_id=None, batch_size=None, limit=None, progress=None):
    doc_id = doc_id or Path(path).stem
    batch_size = batch_size or config.INGEST_BATCH_SIZE

    store.ensure_collection()
    qdrant = store.client()

    started = time.monotonic()
    pieces = chunk.chunks(pdf.pages(path))
    if limit:
        pieces = islice(pieces, limit)

    stored = 0
    for batch in _batched(pieces, batch_size):
        vectors = embeddings.embed_batch([c["text"] for c in batch])
        store.upsert_chunks(batch, vectors, doc_id, qdrant=qdrant)
        stored += len(batch)
        if progress:
            progress(stored, time.monotonic() - started)

    return {"doc_id": doc_id, "chunks": stored, "seconds": round(time.monotonic() - started, 1)}


def _batched(iterable, size):
    batch = []
    for item in iterable:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def main(argv=None):
    args = _parse(argv)

    def report(done, elapsed):
        rate = done / elapsed if elapsed else 0
        print(f"  {done} chunks, {elapsed:.0f}s, {rate:.1f} chunks/s", flush=True)

    try:
        result = ingest(
            args.path,
            doc_id=args.doc_id,
            batch_size=args.batch_size,
            limit=args.limit,
            progress=report if not args.quiet else None,
        )
    except (pdf.PdfError, embeddings.EmbeddingsError) as exc:
        print(exc, file=sys.stderr)
        return 1

    print(f"\n{result['chunks']} chunks stored as {result['doc_id']} in {result['seconds']}s")
    print(f"collection now holds {store.describe()['points']} points")
    return 0


def _parse(argv):
    parser = argparse.ArgumentParser(prog="ragops.ingest")
    parser.add_argument("path")
    parser.add_argument("--doc-id", default=None, help="defaults to the filename")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--limit", type=int, default=None, help="stop after N chunks")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
