"""
Test configuration and fixtures for pytest
"""

import pytest


@pytest.fixture
def sample_metadata():
    return {
        "pdf_path": "test.pdf",
        "total_transactions": 10,
        "previous_balance": 1000.00,
        "total_amount": 1500.00,
        "expected_change": 500.00,
        "transaction_sum": 500.00,
        "validation_passed": True,
        "year": 2024,
        "cardholders": [
            {"name": "John Doe", "card": "1234 5678 9012 3456"},
            {"name": "Jane Doe", "card": "9876 5432 1098 7654"},
        ],
    }


@pytest.fixture
def sample_transactions():
    return [
        {
            "date_transaction_day": "15",
            "date_transaction_month": "01",
            "date_inscription_day": "15",
            "date_inscription_month": "01",
            "description": "TEST STORE",
            "city": "MONTREAL",
            "province": "QC",
            "bonidollars": "1,00 %",
            "amount": 100.50,
            "is_refund": False,
            "foreign_currency": None,
            "foreign_amount": None,
            "exchange_rate": None,
        },
        {
            "date_transaction_day": "16",
            "date_transaction_month": "01",
            "date_inscription_day": "16",
            "date_inscription_month": "01",
            "description": "REFUND STORE",
            "city": "TORONTO",
            "province": "ON",
            "bonidollars": "",
            "amount": -50.25,
            "is_refund": True,
            "foreign_currency": "USD",
            "foreign_amount": 38.50,
            "exchange_rate": 1.30,
        },
        {
            "date_transaction_day": "08",
            "date_transaction_month": "01",
            "date_inscription_day": "08",
            "date_inscription_month": "01",
            "description": "PAIEMENT AUTORISÉ - PRÉLÈVEMENT EFFECTUÉ",
            "city": "",
            "province": "",
            "bonidollars": "",
            "amount": -7049.05,
            "is_refund": True,
            "foreign_currency": None,
            "foreign_amount": None,
            "exchange_rate": None,
        },
    ]


@pytest.fixture
def mock_firefly_env(monkeypatch):
    monkeypatch.setenv("FIREFLY_API_URL", "https://firefly.example.com")
    monkeypatch.setenv("FIREFLY_API_TOKEN", "test-token-123")
