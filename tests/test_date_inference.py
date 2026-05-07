"""Test date inference from filenames."""

import pytest
from cli.date_inference import infer_dates_from_filename, infer_dates_for_pdf
from pathlib import Path


def test_date_inference_yyyymmdd():
    """Test YYYYMMDD format."""
    start, end = infer_dates_from_filename("20240131.pdf")
    assert start == "2024-01-01"
    assert end == "2024-01-31"


def test_date_inference_yyyy_mm_dd():
    """Test YYYY-MM-DD format."""
    start, end = infer_dates_from_filename("2024-01-31.pdf")
    assert start == "2024-01-01"
    assert end == "2024-01-31"


def test_date_inference_invalid():
    """Test invalid filename format."""
    start, end = infer_dates_from_filename("statement.pdf")
    assert start is None


def test_inference_error_message():
    """Test helpful error message."""
    with pytest.raises(ValueError) as exc_info:
        infer_dates_for_pdf(Path("statement.pdf"))

    assert "Could not infer dates" in str(exc_info.value)
    assert "YYYYMMDD.pdf" in str(exc_info.value)
