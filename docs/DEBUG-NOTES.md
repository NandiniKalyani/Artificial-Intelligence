# Debug notes

Things that went wrong and what they turned out to be. Written at the time, so
the wrong guesses stay in.

## The model never stops talking

**Symptom.** First real request to LocalAI came back with a correct one sentence
answer, "A SharePoint site collection is a group of related sites that share
common features, settings, and permissions within Microsoft SharePoint", followed
by about ninety blank lines. `completion_tokens` was exactly
120, which was the `max_tokens` I had sent. Same on every request. So it was
never finishing, it was being cut off.

**What I thought it was.** I had put `stopwords` under `parameters:` in the
model YAML. LocalAI documents it at the top level, so I assumed it was being
silently ignored and the model had no stop tokens at all. Moved it up, restarted
the container, ran the same question.

**What it actually was.** No change, still 120 tokens and still padded with
newlines. So the YAML was not the problem. Sending `stop` on the request itself
does work: with `"stop": ["\n\n"]` the response came back empty after 2 tokens,
which also told me the answer starts with two newlines. So the plumbing is fine,
the model simply never emits `<|end|>` through the chat endpoint and pads
instead.

**Then it got worse.** Sending the stops from the client killed the blank lines,
but the model started answering and then writing its own follow up questions and
answering those too, all the way to `max_tokens`. Looking again at the response,
`prompt_tokens` was 12 for a system message plus a question. Far too few. The
roles were never being rendered.

**What it actually was.** No chat template on the model. LocalAI was handing
llama.cpp the raw text with no `<|system|>`, `<|user|>` or `<|assistant|>`
markers, so Phi had no reason to think a turn had ended and just kept writing.
Adding the template to the YAML fixed it in one restart.

**Fix.** Chat template in the model config. Same question afterwards: "A
SharePoint site collection is a grouping of SharePoint sites that share common
features, permissions, and administration settings within a single site
collection." One sentence, nothing after it. Kept the request level stops and the
newline trimming in the client as well, they are cheap and the model is not the
only thing that can send junk back.

**What it cost.** Around 90 wasted tokens per answer. On CPU that is real,
roughly 20 seconds of generation producing nothing.

## A grounded answer takes two minutes, and it is not the answering

**Symptom.** The chat CLI answers in 8 to 17 seconds warm. The first /ask call
with five retrieved chunks took 147 seconds warm, and the next one timed out at
the 180 second limit I had set.

**What I thought it was.** Generation. A longer, more careful answer from a
grounded prompt, taking longer to produce.

**What it actually was.** Reading the prompt. The answers were 90 tokens either
way. What changed was prompt_tokens: 12 from the CLI, 429 with three chunks, 942
with five. Three warm timings from LocalAI's own log:

| prompt_tokens | seconds |
| --- | --- |
| 429 | 75 |
| 537 | 100 |
| 942 | 147 |

That is about 7 tokens a second for prompt processing on this CPU. Every chunk of
retrieved context costs roughly 25 seconds before the first answer token exists.

**What I did about it.** Raised the timeout to 400 so k of 5 does not fail, kept
the default k at 3, and wrote it up as its own issue. The fix is not in this code.
It is somewhere in LocalAI's thread and batch settings, whether the AVX512 build
is being used (the log says it loaded the AVX2 variant on a CPU that has
AVX512), prompt caching, or shorter chunks. Each of those is a measurement, not a
guess, and they belong together.

**What it means for the design.** The context budget is not a token limit
problem. 942 tokens is a quarter of the 4096 window. It is a time problem, and
the right k is decided by how long a person will wait as much as by retrieval
quality.
