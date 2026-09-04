# Decisions

Choices that could have gone another way, and why they went this way. Written as
I make them, so some of these will look wrong later. I will add the correction
underneath rather than edit the entry.

## Phi-3.5-mini, not something larger

3.8B parameters is about the ceiling for CPU only. I tried nothing bigger,
because the arithmetic is not close: a 7B model at the same quantisation is
roughly double the memory and more than double the time per token, and this has
to run on a laptop while I am doing other things.

The job here is not general reasoning. It is reading three or four retrieved
passages and answering from them. A small model is fine at that, and when the
answer is wrong it is usually retrieval that was wrong, not the model.

## Q4_K_M quantisation, not Q6_K

Q6_K is closer to the original weights and about 2.9GB. Q4_K_M is about 2.2GB
and measurably quicker to first token on this machine.

I went with Q4_K_M because the extra quality in Q6 does not show up in this kind
of task, where the answer is mostly extracted from the context rather than
recalled from the weights. Worth revisiting if answers start drifting from the
passages, since that is the failure mode quantisation would cause.

## Context size 4096, not 8192

The model supports far more, but the KV cache grows with the context and it is
plain RAM here. 4096 leaves room for a system prompt, four retrieved chunks of
around 600 tokens, the question, and the answer. If context budgeting turns out
to be tight when retrieval is real, this is the number to raise first.

## Model config lives in the repo, weights do not

`deploy/localai/models/` holds the YAML and is committed. LocalAI downloads the
`.gguf` into the same directory, which is gitignored. Keeps the mount to one
path and keeps a 2.2GB file out of git.

## The healthcheck runs a real inference

The obvious healthcheck is `GET /v1/models`, which is what I started with. It
answers within seconds of the container starting and stays wrong for about
another two minutes, because that is when the model is actually being read off
disk and into memory. A healthcheck that goes green while the thing cannot
answer is worse than none, since compose will happily start dependents against
it.

So the check asks for a single token and looks for `choices` in the reply. It
costs one real inference, which is why the interval is 5 minutes rather than the
usual 30 seconds. Once the model is loaded that call is quick, so the ongoing
cost is small.

The alternative was a startup probe separate from the liveness probe, which is
what I would do in Kubernetes. Compose has no such split, only `start_period`,
so this is the closest equivalent.

## Embeddings are a separate service, not an import

The API could import sentence-transformers and call it directly. That ties the
API's memory footprint and startup time to a machine learning model, and means
restarting the API to change a route reloads the model as well.

Behind an HTTP boundary the model loads once, restarts on its own, and can be
swapped for a different one without touching the API. The cost is a network hop
per embedding, which is why the batch endpoint in the next issue matters.

## The model is baked into the image

The alternative is downloading it on first start into a mounted cache volume.
That makes a clean clone behave differently from a warm machine, and adds a
volume whose contents have to stay in step with the code.

MiniLM is about 90MB, so it goes in the image. Builds are slower and the image
is bigger, starts are fast and offline. Worth revisiting if the model ever gets
large enough that the image becomes awkward to move around.

## The embeddings healthcheck does not embed

The LocalAI healthcheck runs a real inference because loading takes over two
minutes and there is no cheaper way to know it is ready. MiniLM loads in
seconds, and `/health` already reports ok only after the model has embedded a
string at startup. Repeating that work every 30 seconds forever would buy
nothing.

## Batch embedding, and why 256

Ingesting a document means embedding hundreds of chunks. One at a time, 100
chunks took 26.2s. In a single batch call it took 3.5s, so 7.5 times quicker.
Almost all of that is the model batching internally rather than the HTTP round
trip being avoided.

The cap is 256 texts per request. It has to be something: a whole large document
in one call would hold the request open for a long time and give the caller no
progress at all. Internally `encode` uses a batch size of 32, which is what
keeps memory flat while still filling the CPU.

Empty strings are rejected across the whole list rather than skipped. Silently
dropping one would misalign the returned vectors with the chunks that were sent,
which is the sort of bug that only shows up as bad search results weeks later.

## One collection, not one per document

A collection per document is tempting: deleting a document is a single drop, and
searching one document needs no filter at all.

It falls apart everywhere else. Asking a question across the whole corpus means
querying every collection and merging the scores yourself, which is exactly the
work the vector store exists to do. Qdrant also holds an index per collection,
so a few hundred documents becomes a few hundred indexes.

So: one collection called `docs`, with `doc_id` in the payload and a keyword
index on it. Searching one document is a filter, searching everything is the
default, and deleting a document is a delete by filter rather than a drop. The
filter costs a little, and without the index it would cost a lot more, which is
why the index goes in at creation rather than being added when it starts to
hurt.

## Cosine, not dot product

The embeddings come back normalised, so cosine and dot product rank identically
and there is no measurable difference today. Cosine is still what the collection
is configured with, because it says what is meant. If a future model returns
unnormalised vectors, dot product would silently start ranking by length as well
as direction, and nothing would look broken.

## Point ids are derived, not random

A point id of `uuid5(doc_id + chunk position)` means ingesting the same document
twice overwrites its chunks rather than storing a second copy of every one. With
random ids I would have to delete the document first every time, and forgetting
that once would leave duplicates that quietly skew every search afterwards.

## The passage text is stored in the payload

Qdrant returns ids and scores. An id and a score tell you nothing about whether
retrieval worked, so the text goes in the payload next to the vector and comes
back with the hit. It costs storage, and it is the difference between debugging
retrieval and guessing at it.

## First retrieval numbers, measured on six passages

Four questions, worded to avoid the vocabulary of the passages. The correct
passage came first for two of them and was in the top three for all four.

The two misses are worth keeping. "Why can this person still see the file after I
removed them from the group" returned the sharing links passage at 0.241, with
permission inheritance third. Nothing scored well, which suggests the passage
that answers it does not contain the words the question implies.

"How do I stop staff sending documents to people outside the company" returned
sharing links first at 0.366 and external sharing second. That is arguably a
better answer than the one I expected, since sharing links are how documents
leave the organisation. My label was the debatable part, not the retrieval.

Six passages is too small to conclude anything. It does say the round trip works
and gives a baseline to compare against once chunking is real.

## Settings live in the environment, including the system prompt

The embeddings service had its batch size, request cap and vector dimension as
constants in the code, so tuning any of them meant an edit and a rebuild. They
are environment variables now, passed in through compose, with the same defaults
as before.

The system prompt moved out of llm.py as well. That one is arguable, since it is
closer to code than to configuration. It went anyway, because changing its
wording changes the answers, and that is exactly the sort of thing worth being
able to try three versions of without touching a file.

The dimension is deliberately still checked against the model at startup rather
than trusted. Changing the model without changing the number is the mistake to
catch on the first request instead of discovering later, when every stored
vector is quietly the wrong shape.

## Extraction yields pages, it does not return a document

`pages()` is a generator. The alternative, returning one string for the whole
file, is simpler to use and would have been fine on the two page test file I
nearly used instead.

The real corpus is 1798 pages and 2.24 million characters. Building that as a
single string before chunking has even started is the kind of thing that works
until the document gets big, and then fails in a way that looks like a chunking
problem.

Yielding also keeps the page number attached to the text, which is what makes it
possible to tell someone which page an answer came from.

## Pages with no text are skipped, not yielded empty

pypdf returns an empty string for cover pages, full page diagrams and scans, with
no error and no indication that anything is wrong. Five of the 1798 pages in the
SharePoint export are like this.

Yielding them as empty pages would push chunks of nothing into the vector store,
where they would embed to something meaningless and could be retrieved. Skipping
them means the page numbers in the output are not contiguous, which is the right
trade: a gap in the numbering is visible, a chunk of nothing is not.

The count is reported by `summarise()` so the number is known rather than hidden.
If it were 500 rather than 5, that would be a scanned document and a different
problem entirely.

## Hyphenated line breaks are rejoined

A line ending in a hyphen is nearly always a word split across lines by layout.
"permis-
sions" and "permissions" embed to different vectors, and only one of
them matches a question about permissions.
