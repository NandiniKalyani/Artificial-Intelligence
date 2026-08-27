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
