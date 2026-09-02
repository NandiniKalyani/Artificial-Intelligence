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

# first request after a restart loads 2.2GB off disk, so the timeout has to
# cover that and not just generation
LLM_TIMEOUT = _float("LLM_TIMEOUT", 180)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBEDDINGS_URL = os.getenv("EMBEDDINGS_URL", "http://localhost:8082")

# one collection for everything, filtered by document id at query time. See
# docs/DECISIONS.md for why not one collection per document
COLLECTION = os.getenv("QDRANT_COLLECTION", "docs")
VECTOR_SIZE = _int("VECTOR_SIZE", 384)
