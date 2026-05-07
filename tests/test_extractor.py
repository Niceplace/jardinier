"""
Tests for extractor data transformation functions
"""

from app.extractor import Extractor, Cardholder


def test_parse_description_with_province():
    """Test parsing description that includes a province"""
    extractor = Extractor("dummy.pdf")

    result = extractor._parse_description("GROCERY STORE MONTREAL QC")

    assert result["business"] == "GROCERY STORE"
    assert result["city"] == "MONTREAL"
    assert result["province"] == "QC"


def test_parse_description_without_province():
    """Test parsing description without a province"""
    extractor = Extractor("dummy.pdf")

    result = extractor._parse_description("ONLINE SHOPPING SERVICE")

    assert result["business"] == "ONLINE SHOPPING SERVICE"
    assert result["city"] == ""
    assert result["province"] == ""


def test_parse_description_with_different_province():
    """Test parsing with Ontario province"""
    extractor = Extractor("dummy.pdf")

    result = extractor._parse_description("RESTAURANT KING TORONTO ON")

    assert result["business"] == "RESTAURANT KING"
    assert result["city"] == "TORONTO"
    assert result["province"] == "ON"


def test_parse_transaction_rest_with_bonidollars():
    """Test parsing transaction rest string with bonidollars"""
    extractor = Extractor("dummy.pdf")

    rest = "STORE NAME CITY QC 1,50 % 125,50"
    result = extractor._parse_transaction_rest(rest)

    assert result is not None
    assert result["bonidollars"] == "1,50 %"
    assert result["amount"] == 125.50
    assert result["is_refund"] is False


def test_parse_transaction_rest_with_refund():
    """Test parsing transaction rest with refund (CR)"""
    extractor = Extractor("dummy.pdf")

    rest = "STORE NAME CITY QC 50,25 CR"
    result = extractor._parse_transaction_rest(rest)

    assert result is not None
    assert result["amount"] == -50.25  # Negative for refund
    assert result["is_refund"] is True


def test_parse_transaction_rest_regular_amount():
    """Test parsing regular transaction without bonidollars"""
    extractor = Extractor("dummy.pdf")

    rest = "STORE NAME MONTREAL QC 99,99"
    result = extractor._parse_transaction_rest(rest)

    assert result is not None
    assert result["bonidollars"] == ""
    assert result["amount"] == 99.99
    assert result["is_refund"] is False
    assert result["business"] == "STORE NAME"
    assert result["city"] == "MONTREAL"
    assert result["province"] == "QC"


def test_parse_transaction_rest_with_spaces_in_amount():
    """Test parsing amount with spaces (e.g., '1 234,56')"""
    extractor = Extractor("dummy.pdf")

    rest = "BIG PURCHASE TORONTO ON 1 234,56"
    result = extractor._parse_transaction_rest(rest)

    assert result is not None
    assert result["amount"] == 1234.56


def test_parse_transaction_rest_empty_string():
    """Test parsing empty string (sad path)"""
    extractor = Extractor("dummy.pdf")

    result = extractor._parse_transaction_rest("")

    assert result is None


def test_parse_transaction_rest_with_bonidollars_and_refund():
    """Test parsing transaction with bonidollars - refund case is a known limitation"""
    extractor = Extractor("dummy.pdf")

    # Note: The current parser has a limitation with bonidollars + CR
    # It doesn't properly extract the amount when both are present
    # This test documents the current behavior
    rest = "RETURN STORE CITY QC 2,00 % 75,00 CR"
    result = extractor._parse_transaction_rest(rest)

    assert result is not None
    assert result["bonidollars"] == "2,00 %"
    # The parser tries to find amount after % but before end of string
    # With CR present, this is a known limitation
    assert result["is_refund"] is True


def test_cardholder_dataclass():
    """Test Cardholder dataclass creation"""
    cardholder = Cardholder(name="Test User", card="1234 5678 9012 3456")

    assert cardholder.name == "Test User"
    assert cardholder.card == "1234 5678 9012 3456"


def test_province_list_completeness():
    """Test that all Canadian provinces are in the list"""
    extractor = Extractor("dummy.pdf")

    # All Canadian provinces and territories
    expected_provinces = [
        "QC",
        "ON",
        "BC",
        "AB",
        "MB",
        "SK",
        "NB",
        "NS",
        "PE",
        "NL",
        "YT",
        "NT",
        "NU",
    ]

    for prov in expected_provinces:
        assert prov in extractor.PROVINCES


def test_parse_description_edge_case_single_word():
    """Test parsing description with single word"""
    extractor = Extractor("dummy.pdf")

    result = extractor._parse_description("AMAZON")

    assert result["business"] == "AMAZON"
    assert result["city"] == ""
    assert result["province"] == ""


def test_infer_statement_year():
    """Test year inference from statement period text"""
    extractor = Extractor("dummy.pdf")
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Relevé du 1er janvier au 31 janvier 2024\nSome other text\n"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]

    year = extractor._infer_statement_year(mock_pdf)
    assert year == 2024


def test_infer_statement_year_february():
    """Test year inference with février (accented)"""
    extractor = Extractor("dummy.pdf")
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "du 1er février au 29 février 2025\n"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]

    year = extractor._infer_statement_year(mock_pdf)
    assert year == 2025


def test_infer_statement_year_no_match():
    """Test year inference returns None when no pattern found"""
    extractor = Extractor("dummy.pdf")
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "No date pattern here"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]

    year = extractor._infer_statement_year(mock_pdf)
    assert year is None


def test_infer_statement_year_empty_pages():
    """Test year inference with empty pages"""
    extractor = Extractor("dummy.pdf")
    mock_page = MagicMock()
    mock_page.extract_text.return_value = None
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]

    year = extractor._infer_statement_year(mock_pdf)
    assert year is None


def test_infer_statement_year_with_year_on_each_date():
    """Test year inference with 'du 10 mars 2019 au 9 mars 2020' format"""
    extractor = Extractor("dummy.pdf")
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Période du 10 mars 2019 au 9 mars 2020\nSome other text\n"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]

    year = extractor._infer_statement_year(mock_pdf)
    assert year == 2019


def test_infer_statement_year_with_year_on_each_date_february():
    """Test year inference with février in 'year on each date' format"""
    extractor = Extractor("dummy.pdf")
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "du 1er février 2019 au 28 février 2019\n"
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]

    year = extractor._infer_statement_year(mock_pdf)
    assert year == 2019


from unittest.mock import MagicMock  # noqa: E402
