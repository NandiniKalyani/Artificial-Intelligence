"""The chunking arithmetic, which retrieval now depends on.

No Qdrant, no model, no containers. These are pure functions and the tests
should run in under a second.
"""

import pytest

from ragops import chunk, config

SIZE = 50
OVERLAP = 10


def page(words, number=1):
    return [(number, " ".join(f"w{i}" for i in range(words)))]


def texts(pages, size=SIZE, overlap=OVERLAP):
    return [c["text"] for c in chunk.chunks(pages, size, overlap)]


def test_short_page_is_one_chunk():
    assert len(texts(page(30))) == 1


def test_no_chunk_is_longer_than_the_size():
    assert all(len(t.split()) <= SIZE for t in texts(page(500)))


def test_neighbours_actually_overlap():
    first, second = texts(page(120))[:2]
    tail = first.split()[-OVERLAP:]
    assert second.split()[:OVERLAP] == tail


def test_every_word_survives():
    words = set(f"w{i}" for i in range(300))
    seen = set()
    for t in texts(page(300)):
        seen.update(t.split())
    assert seen == words


def test_a_trailing_fragment_is_not_stored_twice():
    # 105 words at size 50 and overlap 10 leaves a tail of 5, which is already
    # inside the chunk before it. Storing it again is a near duplicate vector
    # competing with the real one
    chunks = texts(page(105))
    assert all(len(c.split()) > OVERLAP for c in chunks)


def test_chunks_do_not_span_pages():
    pages = [(1, "alpha " * 30), (2, "beta " * 30)]
    for c in texts(pages):
        assert not ("alpha" in c and "beta" in c)


def test_page_number_travels_with_the_chunk():
    pages = [(7, "word " * 60), (9, "other " * 60)]
    produced = list(chunk.chunks(pages, SIZE, OVERLAP))
    assert {c["page"] for c in produced} == {7, 9}


def test_chunk_index_keeps_counting_across_pages():
    pages = [(1, "word " * 120), (2, "word " * 120)]
    produced = list(chunk.chunks(pages, SIZE, OVERLAP))
    assert [c["chunk"] for c in produced] == list(range(len(produced)))


def test_pages_below_the_floor_produce_nothing():
    assert texts(page(config.MIN_CHUNK_WORDS - 1)) == []


def test_empty_page_produces_nothing():
    assert texts([(1, "")]) == []


def test_overlap_must_be_smaller_than_the_size():
    with pytest.raises(ValueError):
        list(chunk.chunks(page(100), 50, 50))


def test_the_biggest_chunk_still_fits_the_model():
    """The default size must stay inside the 256 word piece limit.

    all-MiniLM-L6-v2 truncates silently past 256 word pieces, and this corpus
    measures at 1.24 word pieces per word. If someone raises CHUNK_WORDS past
    about 205, embeddings start losing their tails with nothing in any log.
    """
    worst_case = config.CHUNK_WORDS * 1.24
    assert worst_case < 254


def test_boundaries_currently_ignore_sentences(monkeypatch):
    """Documents what it does today, not what it should do.

    Boundaries land on word count, so a chunk can start mid sentence. Written
    down as a test so that when sentence aware splitting arrives, this test
    fails and has to be updated deliberately.
    """
    monkeypatch.setattr(config, "MIN_CHUNK_WORDS", 1)
    text = "alpha beta gamma. delta epsilon zeta. eta theta iota."
    first = list(chunk.chunks([(1, text)], 5, 1))[0]["text"]
    assert first == "alpha beta gamma. delta epsilon"
