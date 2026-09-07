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


@app.get("/documents/{doc_id}")
def status(doc_id: str):
    if doc_id not in documents:
        raise HTTPException(status_code=404, detail="no such document")
    return documents[doc_id]


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
