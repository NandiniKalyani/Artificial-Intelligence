"""HTTP in front of ingestion.

Upload returns as soon as the file is on disk and looks like a PDF. Ingestion
runs behind it, because the SharePoint export takes 149 seconds and no client
should be asked to hold a POST open for that.
"""

import shutil
import time
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile

from ragops import config, embeddings, ingest, pdf, store

app = FastAPI(title="ragops api")

UPLOADS = Path(config.UPLOAD_DIR)

# what happened to each document, keyed by id. In memory, so a restart loses it.
# Fine while ingestion is a foreground concern of whoever uploaded the file, and
# the first thing to move into qdrant when it is not
documents = {}


@app.post("/documents", status_code=202)
def upload(file: UploadFile, background: BackgroundTasks):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="only pdf files are accepted")

    doc_id = _doc_id(file.filename)
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / f"{doc_id}.pdf"

    size = _save(file, path)
    if size == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="file is empty")

    # opening it here rather than in the background task, so a file that is not
    # really a PDF is rejected on the request that sent it instead of failing
    # somewhere the caller cannot see
    try:
        pages = _page_count(path)
    except pdf.PdfError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    documents[doc_id] = {
        "doc_id": doc_id,
        "filename": file.filename,
        "pages": pages,
        "bytes": size,
        "status": "queued",
        "chunks": 0,
        "uploaded_at": time.time(),
    }
    background.add_task(_ingest, doc_id, path)
    return documents[doc_id]


@app.get("/documents")
def list_documents():
    """What is really in the collection, not what this process remembers.

    The status dict only knows about uploads this process handled, and a restart
    empties it. Qdrant knows what is actually searchable, so the list comes from
    there and the upload record is merged on top when there is one.
    """
    listed = []
    for record in store.list_documents():
        known = documents.get(record["doc_id"], {})
        listed.append({**record, "status": known.get("status", "ingested"), "filename": known.get("filename")})
    return {"documents": listed}


@app.get("/documents/{doc_id}")
def status(doc_id: str):
    if doc_id in documents:
        return documents[doc_id]

    # uploaded before a restart, or ingested from the command line. It is still
    # searchable, so a 404 would be a lie
    for record in store.list_documents():
        if record["doc_id"] == doc_id:
            return {**record, "status": "ingested"}

    raise HTTPException(status_code=404, detail="no such document")


@app.get("/documents/{doc_id}/chunks")
def chunks(doc_id: str, page: int = None, limit: int = 20, offset: int = 0):
    if limit > 100:
        raise HTTPException(status_code=400, detail="limit is capped at 100")

    result = store.get_chunks(doc_id, page=page, limit=limit, offset=offset)
    if result["total"] == 0:
        raise HTTPException(status_code=404, detail="no chunks for that document or page")
    return result


@app.get("/search")
def search(q: str, k: int = None, doc_id: str = None, min_score: float = None):
    """Nearest chunks to a question, with their scores.

    The scores are the point. On this corpus a good match scored 0.665 and
    every failed search sat in a flat band between 0.43 and 0.45, so a caller
    can tell "found it" from "nothing matched" without knowing the answer.
    """
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="q is empty")

    k = k or config.SEARCH_K
    if k < 1 or k > config.SEARCH_MAX_K:
        raise HTTPException(status_code=400, detail=f"k must be between 1 and {config.SEARCH_MAX_K}")

    started = time.monotonic()
    try:
        vector = embeddings.embed(q)
    except embeddings.EmbeddingsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    hits = store.search(vector, limit=k, doc_id=doc_id, min_score=min_score)
    scores = [h["score"] for h in hits]

    return {
        "q": q,
        "k": k,
        "hits": hits,
        # top and spread together are what say whether anything matched: a high
        # top with a wide spread is a clear winner, a low top with a narrow
        # spread is the flat band
        "top_score": max(scores) if scores else None,
        "spread": round(max(scores) - min(scores), 3) if len(scores) > 1 else None,
        "seconds": round(time.monotonic() - started, 3),
    }


@app.get("/health")
def health():
    collection = None
    try:
        collection = store.describe()
    except Exception:
        raise HTTPException(status_code=503, detail="qdrant is not answering")
    return {"status": "ok", "collection": collection}


def _ingest(doc_id, path):
    documents[doc_id]["status"] = "ingesting"
    try:
        result = ingest.ingest(
            path,
            doc_id=doc_id,
            progress=lambda done, _elapsed: documents[doc_id].update(chunks=done),
        )
    except (pdf.PdfError, embeddings.EmbeddingsError) as exc:
        documents[doc_id].update(status="failed", error=str(exc))
        return
    documents[doc_id].update(status="done", chunks=result["chunks"], seconds=result["seconds"])


def _save(file, path):
    with path.open("wb") as out:
        shutil.copyfileobj(file.file, out, length=1024 * 1024)
    return path.stat().st_size


def _page_count(path):
    from pypdf import PdfReader

    try:
        return len(PdfReader(str(path)).pages)
    except Exception as exc:
        raise pdf.PdfError("this does not open as a pdf") from exc


def _doc_id(filename):
    stem = Path(filename).stem.lower()
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in stem)[:40].strip("-")
    return f"{safe or 'document'}-{uuid.uuid4().hex[:8]}"
