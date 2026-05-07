"""Test account validation logic."""

from unittest.mock import Mock, patch

import httpx

from cli.validation import validate_account_id


def test_valid_account_id():
    """Test successful account validation."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 1}

    with patch("httpx.get", return_value=mock_response):
        valid, error = validate_account_id(1, "http://test.com", "token")

    assert valid is True
    assert error is None


def test_account_not_found():
    """Test account ID not found."""
    mock_response = Mock()
    mock_response.status_code = 404

    with patch("httpx.get", return_value=mock_response):
        valid, error = validate_account_id(999, "http://test.com", "token")

    assert valid is False
    assert "does not exist" in error


def test_timeout_on_validation():
    """Test timeout during validation."""
    with patch("httpx.get", side_effect=httpx.TimeoutError("Timeout")):
        valid, error = validate_account_id(1, "http://test.com", "token")

    assert valid is False
    assert "Timeout" in error
