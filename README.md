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
