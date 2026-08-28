"""Talk to the model from a terminal.

    python -m ragops.chat
    python -m ragops.chat "what is a site collection"

No retrieval yet, so it is answering from the weights alone. The point is to
prove the stack works end to end before anything else is built on it.
"""

import argparse
import sys
import time

from .llm import LLM, LLMError

# two exchanges is enough for follow up questions like "and how is that
# different from a subsite" without the context filling up with old turns
HISTORY_TURNS = 2


def main(argv=None):
    args = _parse(argv)
    llm = LLM()

    if not llm.ready():
        print(
            f"model {llm.model} is not being served at {llm.url}\n"
            "start the stack with make up, then make wait",
            file=sys.stderr,
        )
        return 1

    if args.question:
        return _ask_once(llm, " ".join(args.question))

    return _repl(llm)


def _ask_once(llm, question):
    try:
        print(_timed(llm, question)[0])
    except LLMError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


def _repl(llm):
    print("ask something. ctrl-c or an empty line to quit")
    history = []

    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not question:
            return 0

        try:
            answer, seconds = _timed(llm, question, history)
        except LLMError as exc:
            print(f"\n{exc}", file=sys.stderr)
            continue

        print(f"\n{answer}\n[{seconds:.1f}s]")

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        del history[: -HISTORY_TURNS * 2]


def _timed(llm, question, history=None):
    started = time.monotonic()
    answer = llm.ask(question, history=history)
    return answer, time.monotonic() - started


def _parse(argv):
    parser = argparse.ArgumentParser(prog="ragops.chat")
    parser.add_argument("question", nargs="*", help="ask one question and exit")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
