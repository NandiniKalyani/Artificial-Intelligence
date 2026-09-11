import os


def _int(name, default):
    return int(os.getenv(name, default))


def _float(name, default):
    return float(os.getenv(name, default))


LOCALAI_URL = os.getenv("LOCALAI_URL", "http://localhost:8081/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "phi-3.5-mini")

# on CPU this is the difference between a 20 second answer and a 90 second one,
# so keep it tight. Long answers are not the point here, correct ones are
LLM_MAX_TOKENS = _int("LLM_MAX_TOKENS", 300)
LLM_TEMPERATURE = _float("LLM_TEMPERATURE", 0.2)

# has to cover a cold load of 2.2GB and, worse, prompt processing. On this CPU
# the model reads context at about 7 tokens a second, so five chunks is 150s
# before a single answer token appears
LLM_TIMEOUT = _float("LLM_TIMEOUT", 400)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBEDDINGS_URL = os.getenv("EMBEDDINGS_URL", "http://localhost:8082")

# one collection for everything, filtered by document id at query time. See
# docs/DECISIONS.md for why not one collection per document
COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")
VECTOR_SIZE = _int("VECTOR_SIZE", 384)

# kept here rather than in llm.py because changing the wording changes the
# answers, and that is a setting worth being able to try without a code edit
SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "You answer questions about SharePoint and Microsoft 365 administration. "
    "Answer only from the context you are given. If the context does not cover "
    "the question, say so rather than guessing.",
)

# MiniLM takes 256 word pieces and silently truncates past that. This corpus
# runs at 1.24 word pieces per word, so 205 words is the ceiling. 180 leaves
# headroom for denser text and the two special tokens
CHUNK_WORDS = _int("CHUNK_WORDS", 180)

# a sentence that straddles a boundary is otherwise only ever seen as two halves,
# neither of which says what the whole sentence said
CHUNK_OVERLAP_WORDS = _int("CHUNK_OVERLAP_WORDS", 30)

# a page holding only "Feedback" or a heading becomes a chunk of a few words,
# which embeds to something meaningless and can still be returned by a search
MIN_CHUNK_WORDS = _int("MIN_CHUNK_WORDS", 20)

# chunks per embed and upsert round trip. The embeddings service caps a request
# at EMBEDDING_MAX_TEXTS, and smaller batches mean progress is reported more
# often on a document that takes minutes
INGEST_BATCH_SIZE = _int("INGEST_BATCH_SIZE", 128)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

# how many chunks a search returns by default. 3 is a guess, the eval set
# decides the real number. The cap exists because every chunk carries its text.
# For /ask, every extra chunk is about 25 seconds of prompt processing
SEARCH_K = _int("SEARCH_K", 3)
SEARCH_MAX_K = _int("SEARCH_MAX_K", 20)

# below this top score the answer is "the documentation does not cover this"
# rather than a guess. Provisional: it comes from two questions, 0.665 against
# 0.438, and the eval set will move it
ANSWER_MIN_SCORE = _float("ANSWER_MIN_SCORE", 0.5)

# words of retrieved context allowed in one prompt. 4096 tokens minus the
# answer, the system prompt and the question, at about 1.3 tokens a word, is
# roughly 2700 words. 2000 leaves headroom, and it is measured against the
# prompt_tokens the model reports back rather than trusted
CONTEXT_BUDGET_WORDS = _int("CONTEXT_BUDGET_WORDS", 2000)
