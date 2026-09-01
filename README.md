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

Returns a normalised 384 value vector. `/health` reports ok only once the model
is loaded, not as soon as the port opens.

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
