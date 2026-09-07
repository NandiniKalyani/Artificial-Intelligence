"""The text cleanup in extraction. The PDF reading itself needs a real file."""

import pytest

from ragops import pdf


def test_hyphenated_line_break_is_rejoined():
    assert pdf.clean("permis-\nsions") == "permissions"


def test_a_real_hyphenated_word_survives():
    assert pdf.clean("read-only access") == "read-only access"


def test_runs_of_spaces_collapse():
    assert pdf.clean("site    collection") == "site collection"


def test_paragraph_breaks_survive_but_long_gaps_do_not():
    assert pdf.clean("one\n\n\n\n\ntwo") == "one\n\ntwo"


def test_single_newlines_are_kept():
    # a line break inside a list is meaningful, and chunking splits on words
    # anyway, so there is nothing to gain from flattening it here
    assert pdf.clean("first line\nsecond line") == "first line\nsecond line"


def test_surrounding_whitespace_goes():
    assert pdf.clean("   text   ") == "text"


def test_a_missing_file_is_a_pdf_error_not_a_traceback():
    with pytest.raises(pdf.PdfError):
        list(pdf.pages("does-not-exist.pdf"))
