"""Talks to LocalAI. Nothing in here knows about retrieval yet."""

import re

import httpx

from . import config

SYSTEM_PROMPT = (
    "You answer questions about SharePoint and Microsoft 365 administration. "
    "Answer only from the context you are given. If the context does not cover "
    "the question, say so rather than guessing."
)

# Phi never emits its own end token through this endpoint, so the request has to
# carry the stops itself. See docs/DEBUG-NOTES.md
STOP = ["<|end|>", "<|user|>", "<|system|>"]

_TRAILING_BLANKS = re.compile(r"\n{3,}")


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, url=None, model=None, timeout=None):
        self.url = (url or config.LOCALAI_URL).rstrip("/")
        self.model = model or config.LLM_MODEL
        self.timeout = timeout or config.LLM_TIMEOUT

    def ask(self, question, context=None, history=None):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": _with_context(question, context)})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": config.LLM_MAX_TOKENS,
            "temperature": config.LLM_TEMPERATURE,
            "stop": STOP,
        }

        try:
            response = httpx.post(
                f"{self.url}/chat/completions", json=payload, timeout=self.timeout
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"model did not answer within {self.timeout}s, it may still be loading"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"call to {self.url} failed: {exc}") from exc

        return _clean(_first_choice(response.json()))

    def ready(self):
        try:
            response = httpx.get(f"{self.url}/models", timeout=5)
            response.raise_for_status()
        except httpx.HTTPError:
            return False
        return any(m.get("id") == self.model for m in response.json().get("data", []))


def _with_context(question, context):
    if not context:
        return question
    joined = "\n\n".join(context) if isinstance(context, (list, tuple)) else context
    return f"Context:\n{joined}\n\nQuestion: {question}"


def _first_choice(body):
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError(f"unexpected response shape: {body}") from exc


def _clean(text):
    # the model pads the answer with a long run of newlines and only stops when
    # it hits max_tokens. Cheaper to cut them here than to fight the template
    return _TRAILING_BLANKS.sub("\n\n", text).strip()
