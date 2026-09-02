"""Store a handful of passages and search them back.

    python -m ragops.roundtrip

Not part of the application. It exists to prove the embeddings service and
Qdrant agree with each other before ingestion is built on top of them. The
questions deliberately avoid the words used in the passages, because matching on
shared words is what keyword search already does.
"""

import sys

from . import embeddings, store

DOC_ID = "roundtrip-sample"

PASSAGES = [
    "Permission inheritance means a subsite receives the permissions of its parent site. Breaking inheritance creates a unique set of permissions that no longer follows the parent.",
    "A site collection administrator has full control over every site in the collection and can restore items from the second stage recycle bin.",
    "Retention labels can be published to SharePoint sites and applied automatically by an auto labelling policy that matches sensitive information types.",
    "Sharing links can be set to Anyone, People in your organisation, or Specific people. Anyone links do not require the recipient to sign in.",
    "A content type is a reusable group of columns and settings that can be applied across lists and libraries so that similar items are described the same way.",
    "External sharing is controlled at both the tenant level and the site level, and the more restrictive of the two settings applies.",
]

QUESTIONS = [
    ("why can this person still see the file after I removed them from the group", 0),
    ("who can get a deleted document back once it has gone from the bin", 1),
    ("how do I stop staff sending documents to people outside the company", 5),
    ("how can I make sure everything gets described the same way", 4),
]


def main():
    store.ensure_collection()

    vectors = embeddings.embed_batch(PASSAGES)
    stored = store.upsert(PASSAGES, vectors, doc_id=DOC_ID)
    print(f"stored {stored} passages\n")

    hits_at_1 = 0
    for question, expected in QUESTIONS:
        results = store.search(embeddings.embed(question), limit=3)
        top = results[0]

        correct = top["text"] == PASSAGES[expected]
        hits_at_1 += correct

        print(f"Q: {question}")
        print(f"   {'right' if correct else 'WRONG'} at 1, score {top['score']:.3f}")
        print(f"   got:      {top['text'][:90]}")
        if not correct:
            print(f"   expected: {PASSAGES[expected][:90]}")
            positions = [i for i, r in enumerate(results) if r["text"] == PASSAGES[expected]]
            print(f"   expected was at position {positions[0] + 1}" if positions else "   expected not in top 3")
        print()

    print(f"top result correct on {hits_at_1} of {len(QUESTIONS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
