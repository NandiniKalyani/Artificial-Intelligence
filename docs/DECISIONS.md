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

## Chunk size is 180 words, and the model chose it

The number people usually reach for is somewhere between 500 and 1000 tokens.
With this embedding model that would be wrong, and wrong invisibly.

all-MiniLM-L6-v2 takes a maximum of 256 word pieces and truncates past that
without an error. I checked what that means in practice rather than trusting the
number: embedding an 800 token passage, then embedding the same passage with an
extra sentence added at the end, produced vectors with a cosine similarity of
1.0. Identical. The extra sentence had no effect because the model never read it.

So a 600 token chunk with this model is really a 256 token chunk, and the rest is
stored in the payload, returned to the reader, and never represented in the
vector that decides whether it is found.

Measured over 60 pages of the real corpus, the text runs at 1.239 word pieces per
word. Reserving the two special tokens leaves 254, which is about 205 words. 180
is that with headroom for denser than average text.

## Overlap is 30 words

A sentence that straddles a boundary is otherwise only ever seen as two halves,
and neither half says what the sentence said. 30 words is about one long
sentence, which is the unit being protected.

It costs storage and near duplicate vectors. The alternative, no overlap, loses
exactly the sentences that span a boundary, and there is no way to know which
ones those were.

## Chunks do not span pages

In this export a page boundary is usually an article boundary. Joining the end of
one article to the start of the next gives a vector that is a blend of two
subjects and a good match for neither.

The cost is that a genuine paragraph split across a page break becomes two
chunks. The overlap does not help there, because the overlap is within a page.
Worth revisiting if retrieval starts missing answers that sit at page boundaries.

## Chunks under 20 words are dropped

Some pages hold nothing but a heading or the word Feedback. Those became chunks
of one to a few words, which embed to something meaningless and can still be
returned by a search.

The floor removes 52 chunks from this corpus and takes 52 pages out entirely,
1793 down to 1741 pages contributing. That is the honest cost: those pages now
contribute nothing. They also contained nothing worth retrieving.

## Ingestion streams rather than collecting

Pages are yielded, chunks are batched at 128, and each batch is embedded and
upserted before the next page is read. Nothing holds the document.

The simpler version, chunk everything then embed everything then upsert, would
have worked on this corpus. It also puts 2.24 million characters and 2918 vectors
in memory at once, and the first document big enough to break it would fail in
the embedding step, which is not where the mistake was made.

Upserting as it goes also means a crash at chunk 2000 leaves 2000 chunks
searchable rather than losing everything.

## What ingestion actually costs

2918 chunks in 148.8 seconds, about 20 chunks per second, on four CPU cores. The
rate was 20.3 at the start and 19.6 at the end, so it does not degrade as the
collection fills.

Nearly all of that time is embedding. It happens once per document, not per
query, which is why 149 seconds is acceptable and why the batch endpoint mattered
enough to be its own issue.

## Search scores cluster when nothing matches

First real retrieval over the whole corpus, four questions:

| Question | Top score | Correct |
| --- | --- | --- |
| who can restore a document deleted from the recycle bin | 0.665 | yes |
| how do I make sure documents are described the same way | 0.545 | not first, correct at 3 |
| why can this person still see the file after I removed them | 0.454 | no |
| how do I stop staff sending documents outside the company | 0.438 | no |

The useful part is the shape. The good answer scored 0.665 and the three bad ones
all sat between 0.43 and 0.45, with their own top three results within 0.02 of
each other. A flat cluster of mediocre scores is what "nothing in the corpus
matched" looks like.

That makes the score usable as a confidence signal, which is what decides whether
the system answers or says the documentation does not cover the question. The
threshold is not chosen yet, and choosing it needs the eval set rather than these
four questions.

## Tests cover the arithmetic, not the plumbing

The tests are on chunking and the extraction cleanup, because those are pure
functions with edge cases that fail quietly: the overlap step, the trailing
fragment rule, the word floor, the page boundary rule.

Nothing here tests Qdrant, the embeddings service or the model. Those need
containers, take seconds rather than milliseconds, and mostly test that other
people's software works. Integration tests against the running stack are worth
having and are a separate job.

One test is not about chunking at all. It asserts that the configured chunk size
multiplied by the measured 1.24 word pieces per word stays under 254. If somebody
raises the chunk size to a number that sounds reasonable, embeddings start losing
their tails with nothing in any log, and this is the only thing that would say
so.

## Upload returns before ingestion finishes

Ingesting the SharePoint export takes 149 seconds. Doing that inside the POST
means a client holding a connection open for two and a half minutes, a proxy
somewhere deciding that is unreasonable, and no way to report progress.

So the request does the parts that can fail fast, saving the file and opening it
with pypdf, then returns 202 with a document id. The work happens in a background
task and the id is polled for status.

That splits validation across two places on purpose. Anything cheap enough to
check in the request is checked there, so a bad file is rejected by the call that
sent it. Anything expensive happens behind, where failure is reported through the
status rather than the response code.

## Document status is in memory, and that is temporary

`documents` is a dict in the API process. A restart loses every record, and two
API replicas would each know only about their own uploads.

It is honest for where the project is: ingestion is something the person who
uploaded the file waits on for a couple of minutes. It stops being honest the
moment there is more than one replica or anyone expects history, and the fix is
to keep the record in Qdrant alongside the chunks.

## Uploaded files are kept

The PDF stays in a volume after ingestion. It costs disk and it means a chunking
change can be applied to everything already uploaded without asking anyone to
send their document again.

Given issue 35 will change every chunk boundary in the corpus, that is not
hypothetical.
