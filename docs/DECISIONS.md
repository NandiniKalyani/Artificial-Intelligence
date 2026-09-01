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

Q6_K is closer to the original weights and about 3.1GB. Q4_K_M is about 2.4GB
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
path and keeps a 2.4GB file out of git.

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
