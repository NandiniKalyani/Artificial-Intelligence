"""Search, then ask the model to answer from what was found."""

import time

from . import config, embeddings, store
from .llm import LLM


def ask(question, k=None, doc_id=None, llm=None):
    started = time.monotonic()
    k = k or config.SEARCH_K

    hits = store.search(embeddings.embed(question), limit=k, doc_id=doc_id)
    scores = [h["score"] for h in hits]
    top = max(scores) if scores else None
    spread = round(max(scores) - min(scores), 3) if len(scores) > 1 else None
    retrieval_seconds = round(time.monotonic() - started, 3)

    if not hits or top < config.ANSWER_MIN_SCORE:
        # a confident answer here would be the model's training data dressed
        # up as documentation. Saying no is the correct output
        return {
            "answer": "The documentation I have does not appear to cover this.",
            "answered": False,
            "sources": [],
            "top_score": top,
            "spread": spread,
            "retrieval_seconds": retrieval_seconds,
            "seconds": retrieval_seconds,
        }

    kept, dropped = _within_budget(hits)
    context = [f"[page {h['page']}]\n{h['text']}" for h in kept]

    text, usage = (llm or LLM()).ask_with_usage(question, context=context)

    return {
        "answer": text,
        "answered": True,
        "sources": [
            {"page": h["page"], "score": round(h["score"], 3), "chunk": h["chunk"], "doc_id": h["doc_id"]}
            for h in kept
        ],
        "dropped_for_budget": dropped,
        "top_score": top,
        "spread": spread,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "retrieval_seconds": retrieval_seconds,
        "seconds": round(time.monotonic() - started, 1),
    }


def _within_budget(hits):
    """Keep hits in score order until the word budget is spent.

    Dropping the lowest scoring chunks rather than truncating the last one, so
    a chunk is either wholly in the prompt or not there. Half a chunk is the
    thing most likely to produce a confident wrong answer.
    """
    kept, used = [], 0
    for hit in hits:
        words = len(hit["text"].split())
        if used + words > config.CONTEXT_BUDGET_WORDS:
            break
        kept.append(hit)
        used += words
    return kept, len(hits) - len(kept)
