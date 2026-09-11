# ragops

Ask questions about SharePoint and Microsoft 365 administration documentation in
plain language, and get answers with the source passages they came from.

Runs entirely on CPU. No API keys, no cloud inference, nothing leaves the
machine.

## Why

M365 admin documentation is enormous and changes constantly, and search across it
is keyword based. If you do not already know the right term you cannot find the
answer. I spent about ten years working in this stack, so it seemed like a
reasonable thing to point retrieval augmented generation at.

The other reason for this corpus: I know the material well enough to tell whether
an answer is actually correct. That matters more than it sounds, because most of
the work in a RAG system is finding out that retrieval is quietly returning the
wrong passages.

## Status

Early. Setting up the repo structure. See the issues for what is planned.

## Stack

Python, FastAPI, Qdrant, sentence-transformers, LocalAI running Phi-3.5-mini,
Docker Compose.

## Layout

```
services/embeddings   sentence-transformers behind a small HTTP API
services/api          ingestion, retrieval, chat
services/frontend     chat UI
deploy/compose        local stack
deploy/k8s            manifests
eval                  retrieval quality harness
tests
docs
```

## Running it

Docker and Docker Compose are the only requirements so far.

```
cp .env.example .env
make up
make logs
```

That brings up Qdrant and LocalAI. `make wait` blocks until both can actually
serve a request, which on a cold start means waiting for the model download.

 LocalAI pulls its model on first start, which
takes a while and a few GB, so the healthcheck is given a long start period
before compose decides it has failed.

Without make, the same thing:

```
docker compose -f deploy/compose/docker-compose.yml up -d
```

The embeddings service, the API, and the UI are not in the compose file yet. They
go in as they get built.

## Embeddings

```
curl -s http://localhost:8082/embed -H 'Content-Type: application/json'   -d '{"text":"A site collection contains one or more SharePoint sites."}'
```

Returns a normalised 384 value vector. For more than one, `POST /embed/batch`
with `{"texts": [...]}`, up to 256 at a time. Embedding 100 chunks that way took
3.5s against 26s one at a time. `/health` reports ok only once the model
is loaded, not as soon as the port opens.

## Vector store

```
cd services/api
python -m ragops.store           # creates the collection if it is missing
python -m ragops.store --reset   # drops it and starts again
```

One collection, 384 dimensions, cosine distance, with an index on `doc_id` so a
single document can be searched without scanning everything.

## Reading a PDF

```
cd services/api
python -m ragops.pdf ../../data/sharepoint.pdf
python -m ragops.pdf ../../data/sharepoint.pdf --page 42
```

The corpus is the SharePoint admin documentation exported from Microsoft Learn:
1798 pages, 2.24 million characters, about 100 seconds to read end to end. Five
pages have no extractable text and are skipped.

## Chunking

```
cd services/api
python -m ragops.chunk ../../data/sharepoint.pdf --show 3
```

180 words per chunk with 30 words of overlap. The size is set by the model, not
by preference: all-MiniLM-L6-v2 reads 256 word pieces and silently discards
anything past that, and this corpus runs at 1.24 word pieces per word, so 205
words is the hard ceiling.

The SharePoint export produces 2918 chunks from 1798 pages.

## The API

```
make up
curl -F "file=@data/sharepoint.pdf" http://localhost:8000/documents
curl http://localhost:8000/documents/sharepoint-ab12cd34
```

Upload returns 202 with a document id straight away and ingestion carries on
behind it, because the SharePoint export takes 149 seconds and no client should
hold a POST open that long. Poll the id for progress.

Anything that is not a PDF gets 415, an empty file 400, and a file that pypdf
cannot open 400 on the request that sent it rather than failing later where the
caller cannot see it.

## Asking

```
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json"   -d '{"question": "who can restore a document deleted from the recycle bin", "k": 3}'
```

Searches, puts the chunks in front of the model, and returns the answer with the
pages it came from. If the best match scores under 0.5 it says the documentation
does not cover the question instead of guessing.

Slow. About 75 seconds with three chunks and 150 with five, nearly all of it the
model reading the context in at around 7 tokens a second on CPU. That is the
number to fix next, not something to hide.

## Searching

```
curl "http://localhost:8000/search?q=who+can+restore+a+deleted+document&k=5"
curl "http://localhost:8000/search?q=external+sharing&min_score=0.6"
```

Returns the nearest chunks with their scores, plus the top score and the spread
across the results. Those two together say whether anything matched: a good
question here scored 0.665 with a spread of 0.109, a question the corpus does
not answer scored 0.438 with a spread of 0.011. Around 60 to 80ms a query.

## Looking at what is stored

```
curl http://localhost:8000/documents
curl "http://localhost:8000/documents/sharepoint/chunks?limit=2"
curl "http://localhost:8000/documents/sharepoint/chunks?page=932"
```

The list comes from Qdrant rather than from anything the API remembers, so a
document ingested from the command line or uploaded before a restart still shows
up. The chunk endpoint is what I use when a search returns something odd and I
want to read the source text it came from.

## Ingesting a document

```
cd services/api
python -m ragops.ingest ../../data/sharepoint.pdf
python -m ragops.ingest ../../data/sharepoint.pdf --limit 200 --doc-id trial
```

Streams: pages out one at a time, chunks batched, each batch embedded and stored
before the next page is read. The 1798 page SharePoint export becomes 2918 chunks
in 149 seconds, at a steady 20 chunks per second.

## Does search actually work

```
cd services/api
python -m ragops.roundtrip
```

Stores six SharePoint admin passages and asks four questions that share almost
no words with them. Right now the correct passage is top for two of the four,
and in the top three for all four. The output shows where the expected passage
ranked when it was not first.

## Asking it something

```
cd services/api
pip install -r requirements.txt
python -m ragops.chat
```

Or one question and out:

```
python -m ragops.chat "what is a site collection"
```

There is no retrieval yet, so it is answering from the model's own weights. That
is the next phase. This exists to prove the stack works before anything is built
on it.

## Tests

```
pip install -r services/api/requirements-dev.txt
python -m pytest tests -q
```

Chunking arithmetic and the extraction cleanup only. No containers, no model, so
it runs in well under a second. One test asserts that the configured chunk size
still fits inside the embedding model's 256 word piece limit, since exceeding it
fails silently.

## Hooks

Two checks run on every commit. One blocks credentials, the other catches the
writing habits I do not want in a public repo. Install them after cloning:

```
./scripts/install-hooks.sh
```

Both scripts also run standalone if you want to scan everything rather than just
what is staged.

## License

MIT
