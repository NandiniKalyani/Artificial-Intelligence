"""Text out of a PDF, one page at a time.

    python -m ragops.pdf data/sharepoint.pdf
    python -m ragops.pdf data/sharepoint.pdf --page 42

Yields pages rather than returning one big string. A documentation export can be
hundreds of pages, and holding the whole thing in memory before chunking has
even started is the sort of thing that works fine until the file gets big.
"""

import argparse
import re
import sys
import time
from pathlib import Path

from pypdf import PdfReader

# a line ending in a hyphen is almost always a word split across lines. Joining
# them back matters because "permis- sions" and "permissions" embed differently
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_RUNS = re.compile(r"\n{3,}")


class PdfError(RuntimeError):
    pass


def pages(path):
    """Yield (page_number, text) for every page that has usable text.

    Pages with nothing extractable are skipped rather than yielded empty. Cover
    pages, full page diagrams and scans all come back as an empty string, and a
    chunk of nothing is worse than no chunk at all.
    """
    path = Path(path)
    if not path.exists():
        raise PdfError(f"no such file: {path}")

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise PdfError(f"could not open {path}: {exc}") from exc

    for number, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:
            # one broken page should not stop a 400 page document
            continue

        text = clean(raw)
        if text:
            yield number, text


def clean(text):
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    text = _WHITESPACE.sub(" ", text)
    text = _BLANK_RUNS.sub("\n\n", text)
    return text.strip()


def summarise(path):
    reader = PdfReader(str(path))
    total = len(reader.pages)

    started = time.monotonic()
    with_text = 0
    characters = 0
    for _, text in pages(path):
        with_text += 1
        characters += len(text)

    return {
        "pages": total,
        "with_text": with_text,
        "empty": total - with_text,
        "characters": characters,
        "seconds": round(time.monotonic() - started, 1),
    }


def main(argv=None):
    args = _parse(argv)

    try:
        if args.page:
            for number, text in pages(args.path):
                if number == args.page:
                    print(text)
                    return 0
            print(f"page {args.page} has no extractable text", file=sys.stderr)
            return 1

        for key, value in summarise(args.path).items():
            print(f"{key}: {value}")
    except PdfError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def _parse(argv):
    parser = argparse.ArgumentParser(prog="ragops.pdf")
    parser.add_argument("path")
    parser.add_argument("--page", type=int, help="print one page and exit")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
