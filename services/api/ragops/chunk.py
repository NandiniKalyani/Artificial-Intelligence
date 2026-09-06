"""Split page text into pieces small enough that the model actually reads them.

    python -m ragops.chunk data/sharepoint.pdf

The size is not a taste decision. all-MiniLM-L6-v2 has a maximum input of 256
word pieces and truncates silently past that, so anything longer is thrown away
without a warning. Measured on this corpus, the text runs at 1.24 word pieces
per word, which puts the ceiling at about 205 words. The default here is 180,
leaving room for the two special tokens and for denser than average text.
"""

import argparse
import re
import sys

from . import config

# split on sentence ends, keeping the punctuation. Not perfect with
# abbreviations, and the failure is a chunk boundary in a slightly odd place
# rather than lost text
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def chunks(pages, size=None, overlap=None):
    """Yield {text, page, chunk} for a stream of (page number, text) pairs.

    Chunks do not span pages. A page boundary in this corpus is usually an
    article boundary, and joining two unrelated articles into one chunk makes
    the vector a blend of both.
    """
    size = size or config.CHUNK_WORDS
    overlap = overlap or config.CHUNK_OVERLAP_WORDS

    if overlap >= size:
        raise ValueError("overlap must be smaller than the chunk size")

    index = 0
    for page_number, text in pages:
        for piece in _split(text, size, overlap):
            if len(piece.split()) < config.MIN_CHUNK_WORDS:
                continue
            yield {"text": piece, "page": page_number, "chunk": index}
            index += 1


def _split(text, size, overlap):
    words = []
    for sentence in _SENTENCE.split(text):
        words.extend(sentence.split())

    if not words:
        return

    step = size - overlap
    for start in range(0, len(words), step):
        piece = words[start : start + size]
        if not piece:
            break
        # a trailing fragment shorter than the overlap is already contained in
        # the chunk before it, so storing it again adds a near duplicate vector
        if start and len(piece) <= overlap:
            break
        yield " ".join(piece)


def main(argv=None):
    from . import pdf

    args = _parse(argv)

    counts = []
    pages_seen = set()
    skipped = 0
    for chunk in chunks(pdf.pages(args.path), args.size, args.overlap):
        counts.append(len(chunk["text"].split()))
        pages_seen.add(chunk["page"])
        if args.show and chunk["chunk"] < args.show:
            print(f"--- chunk {chunk['chunk']}, page {chunk['page']}, {counts[-1]} words")
            print(chunk["text"][:400])
            print()

    if not counts:
        print("no chunks produced", file=sys.stderr)
        return 1

    print(f"chunks: {len(counts)}")
    print(f"pages with chunks: {len(pages_seen)}")
    print(f"words per chunk: min {min(counts)}, mean {sum(counts) // len(counts)}, max {max(counts)}")
    print(f"estimated word pieces at 1.24 per word: max {int(max(counts) * 1.24)}")
    return 0


def _parse(argv):
    parser = argparse.ArgumentParser(prog="ragops.chunk")
    parser.add_argument("path")
    parser.add_argument("--size", type=int, default=None, help="words per chunk")
    parser.add_argument("--overlap", type=int, default=None, help="words of overlap")
    parser.add_argument("--show", type=int, default=0, help="print the first N chunks")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
