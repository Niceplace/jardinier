"""
Tests for Firefly-III transaction mapping and client
"""

import pytest
from unittest.mock import patch, MagicMock

from app.firefly import (
    _clean_merchant_name,
    _is_cc_payment,
    map_transactions,
    map_bonidollars,
    map_account_transactions,
    build_batch,
    send_batch,
    clear_all_transactions,
    clear_expense_accounts,
    clear_revenue_accounts,
    verify_transactions,
    FireflyClientError,
)

CC_ACCOUNT_ID = 1
CHECKING_ACCOUNT_ID = 2
EXPENSE_ACCOUNT_ID = 3


class TestCleanMerchantName:
    def test_strips_3_digit_prefix(self):
        assert _clean_merchant_name("001 UHC OF QUEBEC") == "UHC OF QUEBEC"

    def test_strips_prefix_with_hash(self):
        assert _clean_merchant_name("006 MAGASIN CDN TIRE #0040") == "MAGASIN CDN TIRE #0040"

    def test_no_prefix_unchanged(self):
        assert _clean_merchant_name("AMAZON.CA") == "AMAZON.CA"

    def test_empty_string(self):
        assert _clean_merchant_name("") == ""

    def test_description_field_unchanged(self):
        """Description field also gets the prefix stripped"""
        transactions = [
            {
                "date_transaction_day": "15",
                "date_transaction_month": "01",
                "description": "001 STORE",
                "city": "",
                "province": "",
                "amount": 10.0,
                "is_refund": False,
                "foreign_currency": None,
                "foreign_amount": None,
            }
        ]
        withdrawals, _, _ = map_transactions(transactions, year=2024, cc_account_id=CC_ACCOUNT_ID)
        assert withdrawals[0]["description"] == "STORE"
        assert withdrawals[0]["destination_name"] == "STORE"


class TestIsCCPayment:
    def test_paiement_autorise(self):
        assert _is_cc_payment("PAIEMENT AUTORISÉ - PRÉLÈVEMENT EFFECTUÉ") is True

    def test_prelevement(self):
        assert _is_cc_payment("PRÉLÈVEMENT EFFECTUÉ") is True

    def test_pmt_web(self):
        assert _is_cc_payment("PMT WEB PAYMENT") is True

    def test_payment_authorized(self):
        assert _is_cc_payment("PAYMENT AUTHORIZED") is True

    def test_case_insensitive(self):
        assert _is_cc_payment("paiement autorisé") is True

    def test_regular_merchant(self):
        assert _is_cc_payment("AMAZON.CA") is False

    def test_regular_refund(self):
        assert _is_cc_payment("OLDNAVY.COM") is False

    def test_empty_string(self):
        assert _is_cc_payment("") is False


class TestMapTransactions:
    def test_withdrawal_mapping(self):
        transactions = [
            {
                "date_transaction_day": "15",
                "date_transaction_month": "01",
                "description": "AMAZON.CA",
                "city": "MONTREAL",
                "province": "QC",
                "amount": 49.99,
                "is_refund": False,
                "foreign_currency": None,
                "foreign_amount": None,
            }
        ]
        withdrawals, deposits, transfers = map_transactions(transactions, year=2024, cc_account_id=CC_ACCOUNT_ID)
        assert len(withdrawals) == 1
        assert len(deposits) == 0
        assert len(transfers) == 0
        w = withdrawals[0]
        assert w["type"] == "withdrawal"
        assert w["amount"] == "49.99"
        assert w["description"] == "AMAZON.CA"
        assert w["date"] == "2024-01-15"
        assert w["source_id"] == CC_ACCOUNT_ID
        assert w["destination_name"] == "AMAZON.CA"
        assert w["notes"] == "MONTREAL, QC"

    def test_refund_mapping(self):
        transactions = [
            {
                "date_transaction_day": "5",
                "date_transaction_month": "02",
                "description": "RETURN SHOP",
                "city": "TORONTO",
                "province": "ON",
                "amount": -25.00,
                "is_refund": True,
                "foreign_currency": None,
                "foreign_amount": None,
            }
        ]
        withdrawals, deposits, transfers = map_transactions(transactions, year=2024, cc_account_id=CC_ACCOUNT_ID)
        assert len(withdrawals) == 0
        assert len(deposits) == 1
        assert len(transfers) == 0
        d = deposits[0]
        assert d["type"] == "deposit"
        assert d["amount"] == "25.0"
        assert d["description"] == "RETURN SHOP"
        assert d["date"] == "2024-02-05"
        assert d["source_name"] == "RETURN SHOP"
        assert d["destination_id"] == CC_ACCOUNT_ID
        assert d["notes"] == "TORONTO, ON"

    def test_cc_payment_mapping(self):
        transactions = [
            {
                "date_transaction_day": "08",
                "date_transaction_month": "01",
                "description": "PAIEMENT AUTORISÉ - PRÉLÈVEMENT EFFECTUÉ",
                "city": "",
                "province": "",
                "amount": -7049.05,
                "is_refund": True,
                "foreign_currency": None,
                "foreign_amount": None,
            }
        ]
        withdrawals, deposits, transfers = map_transactions(
            transactions,
            year=2024,
            cc_account_id=CC_ACCOUNT_ID,
            checking_account_id=CHECKING_ACCOUNT_ID,
        )
        assert len(withdrawals) == 0
        assert len(deposits) == 0
        assert len(transfers) == 1
        t = transfers[0]
        assert t["type"] == "transfer"
        assert t["amount"] == "7049.05"
        assert t["source_id"] == CHECKING_ACCOUNT_ID
        assert t["destination_id"] == CC_ACCOUNT_ID

    def test_cc_payment_skipped_without_account(self):
        transactions = [
            {
                "date_transaction_day": "08",
                "date_transaction_month": "01",
                "description": "PAIEMENT AUTORISÉ - PRÉLÈVEMENT EFFECTUÉ",
                "city": "",
                "province": "",
                "amount": -7049.05,
                "is_refund": True,
                "foreign_currency": None,
                "foreign_amount": None,
            }
        ]
        withdrawals, deposits, transfers = map_transactions(transactions, year=2024, cc_account_id=CC_ACCOUNT_ID)
        assert len(withdrawals) == 0
        assert len(deposits) == 0
        assert len(transfers) == 0

    def test_expense_account_id_override(self):
        transactions = [
            {
                "date_transaction_day": "10",
                "date_transaction_month": "03",
                "description": "STORE",
                "city": "",
                "province": "",
                "amount": 100.0,
                "is_refund": False,
                "foreign_currency": None,
                "foreign_amount": None,
            }
        ]
        withdrawals, _, _ = map_transactions(
            transactions,
            year=2024,
            cc_account_id=CC_ACCOUNT_ID,
            expense_account_id=EXPENSE_ACCOUNT_ID,
        )
        assert withdrawals[0]["destination_id"] == EXPENSE_ACCOUNT_ID
        assert "destination_name" not in withdrawals[0]

    def test_foreign_currency_mapping(self):
        transactions = [
            {
                "date_transaction_day": "20",
                "date_transaction_month": "06",
                "description": "OVERSEAS SHOP",
                "city": "",
                "province": "",
                "amount": 75.50,
                "is_refund": False,
                "foreign_currency": "USD",
                "foreign_amount": 55.00,
            }
        ]
        withdrawals, _, _ = map_transactions(transactions, year=2024, cc_account_id=CC_ACCOUNT_ID)
        assert withdrawals[0]["foreign_currency_code"] == "USD"
        assert withdrawals[0]["foreign_amount"] == "55.0"

    def test_notes_empty_when_no_location(self):
        transactions = [
            {
                "date_transaction_day": "1",
                "date_transaction_month": "01",
                "description": "ONLINE PURCHASE",
                "city": "",
                "province": "",
                "amount": 10.0,
                "is_refund": False,
                "foreign_currency": None,
                "foreign_amount": None,
            }
        ]
        withdrawals, _, _ = map_transactions(transactions, year=2024, cc_account_id=CC_ACCOUNT_ID)
        assert withdrawals[0]["notes"] is None

    def test_date_zero_padding(self):
        transactions = [
            {
                "date_transaction_day": "5",
                "date_transaction_month": "3",
                "description": "SHOP",
                "city": "",
                "province": "",
                "amount": 10.0,
                "is_refund": False,
                "foreign_currency": None,
                "foreign_amount": None,
            }
        ]
        withdrawals, _, _ = map_transactions(transactions, year=2024, cc_account_id=CC_ACCOUNT_ID)
        assert withdrawals[0]["date"] == "2024-03-05"

    def test_three_way_split(self):
        transactions = [
            {
                "date_transaction_day": "1",
                "date_transaction_month": "01",
                "description": "PURCHASE",
                "city": "",
                "province": "",
                "amount": 100.0,
                "is_refund": False,
                "foreign_currency": None,
                "foreign_amount": None,
            },
            {
                "date_transaction_day": "2",
                "date_transaction_month": "01",
                "description": "REFUND",
                "city": "",
                "province": "",
                "amount": -30.0,
                "is_refund": True,
                "foreign_currency": None,
                "foreign_amount": None,
            },
            {
                "date_transaction_day": "3",
                "date_transaction_month": "01",
                "description": "PAIEMENT AUTORISÉ",
                "city": "",
                "province": "",
                "amount": -500.0,
                "is_refund": True,
                "foreign_currency": None,
                "foreign_amount": None,
            },
            {
                "date_transaction_day": "4",
                "date_transaction_month": "01",
                "description": "ANOTHER PURCHASE",
                "city": "",
                "province": "",
                "amount": 20.0,
                "is_refund": False,
                "foreign_currency": None,
                "foreign_amount": None,
            },
        ]
        withdrawals, deposits, transfers = map_transactions(
            transactions,
            year=2024,
            cc_account_id=CC_ACCOUNT_ID,
            checking_account_id=CHECKING_ACCOUNT_ID,
        )
        assert len(withdrawals) == 2
        assert len(deposits) == 1
        assert len(transfers) == 1

    def test_zero_amount_skipped(self):
        transactions = [
            {
                "date_transaction_day": "1",
                "date_transaction_month": "01",
                "description": "ZERO REFUND",
                "city": "",
                "province": "",
                "amount": -0.0,
                "is_refund": True,
                "foreign_currency": None,
                "foreign_amount": None,
            },
            {
                "date_transaction_day": "2",
                "date_transaction_month": "01",
                "description": "NORMAL PURCHASE",
                "city": "",
                "province": "",
                "amount": 50.0,
                "is_refund": False,
                "foreign_currency": None,
                "foreign_amount": None,
            },
        ]
        withdrawals, deposits, transfers = map_transactions(transactions, year=2024, cc_account_id=CC_ACCOUNT_ID)
        assert len(withdrawals) == 1
        assert len(deposits) == 0
        assert len(transfers) == 0


class TestBuildBatch:
    def test_basic_batch(self):
        txns = [
            {"type": "withdrawal", "amount": "10.0", "description": "Test"},
        ]
        batch = build_batch(txns, group_title="Test Group")
        assert batch["group_title"] == "Test Group"
        assert batch["apply_rules"] is False
        assert len(batch["transactions"]) == 1
        assert batch["transactions"][0] == txns[0]

    def test_apply_rules_true(self):
        txns = [{"type": "withdrawal", "amount": "10.0"}]
        batch = build_batch(txns, group_title="G", apply_rules=True)
        assert batch["apply_rules"] is True


class TestSendBatch:
    def test_missing_api_url(self):
        with pytest.raises(FireflyClientError, match="FIREFLY_API_URL"):
            send_batch({}, api_url="", api_token="token")

    def test_missing_api_token(self):
        with pytest.raises(FireflyClientError, match="FIREFLY_API_TOKEN"):
            send_batch({}, api_url="https://example.com", api_token="")

    @patch("app.firefly.httpx.Client")
    def test_successful_send(self, mock_client_cls, mock_firefly_env):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": {"id": "123"}}
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = send_batch(
            {"transactions": [{"type": "withdrawal"}]},
            api_url="https://firefly.example.com/api/v1",
            api_token="test-token-123",
        )
        assert result == {"data": {"id": "123"}}
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://firefly.example.com/api/v1/transactions"
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer test-token-123"
        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"

    @patch("app.firefly.httpx.Client")
    def test_422_response_raises(self, mock_client_cls, mock_firefly_env):
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = '{"message":"Validation failed"}'
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(FireflyClientError, match="422"):
            send_batch(
                {"transactions": []},
                api_url="https://firefly.example.com/api/v1",
                api_token="test-token-123",
            )

    @patch("app.firefly.httpx.Client")
    def test_500_response_raises(self, mock_client_cls, mock_firefly_env):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(FireflyClientError, match="500"):
            send_batch(
                {"transactions": []},
                api_url="https://firefly.example.com/api/v1",
                api_token="test-token-123",
            )


class TestDestroyObjects:
    @patch("app.firefly.httpx.Client")
    def test_clear_transactions(self, mock_client_cls, mock_firefly_env):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_client = MagicMock()
        mock_client.delete.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = clear_all_transactions(
            api_url="https://firefly.example.com/api/v1",
            api_token="test-token-123",
        )
        assert result["status"] == "success"
        assert result["objects"] == "transactions"
        assert mock_client.delete.call_count == 1
        assert "objects=transactions" in mock_client.delete.call_args[0][0]

    @patch("app.firefly.httpx.Client")
    def test_clear_expense_accounts(self, mock_client_cls, mock_firefly_env):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_client = MagicMock()
        mock_client.delete.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = clear_expense_accounts(
            api_url="https://firefly.example.com/api/v1",
            api_token="test-token-123",
        )
        assert result["status"] == "success"
        assert result["objects"] == "expense_accounts"
        assert mock_client.delete.call_count == 1
        assert "objects=expense_accounts" in mock_client.delete.call_args[0][0]

    @patch("app.firefly.httpx.Client")
    def test_clear_revenue_accounts(self, mock_client_cls, mock_firefly_env):
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_client = MagicMock()
        mock_client.delete.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = clear_revenue_accounts(
            api_url="https://firefly.example.com/api/v1",
            api_token="test-token-123",
        )
        assert result["status"] == "success"
        assert result["objects"] == "revenue_accounts"
        assert mock_client.delete.call_count == 1
        assert "objects=revenue_accounts" in mock_client.delete.call_args[0][0]

    def test_missing_api_url(self):
        with pytest.raises(FireflyClientError, match="FIREFLY_API_URL"):
            clear_all_transactions(api_url="", api_token="token")

    @patch("app.firefly.httpx.Client")
    def test_api_error(self, mock_client_cls, mock_firefly_env):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client = MagicMock()
        mock_client.delete.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(FireflyClientError, match="500"):
            clear_all_transactions(
                api_url="https://firefly.example.com/api/v1",
                api_token="test-token-123",
            )


class TestVerifyTransactions:
    def test_no_warnings_on_match(self):
        firefly_response = {
            "data": {
                "created": [
                    {
                        "id": "1",
                        "transactions": [
                            {
                                "attributes": {
                                    "date": "2019-04-15",
                                    "amount": "49.99",
                                    "type": "withdrawal",
                                }
                            }
                        ],
                    }
                ]
            }
        }
        sent = [{"date": "2019-04-15", "amount": "49.99", "type": "withdrawal"}]
        warnings = verify_transactions(firefly_response, sent)
        assert warnings == []

    def test_date_mismatch_warning(self):
        firefly_response = {
            "data": {
                "created": [
                    {
                        "id": "1",
                        "transactions": [
                            {
                                "attributes": {
                                    "date": "2026-04-15",
                                    "amount": "49.99",
                                    "type": "withdrawal",
                                }
                            }
                        ],
                    }
                ]
            }
        }
        sent = [{"date": "2019-04-15", "amount": "49.99", "type": "withdrawal"}]
        warnings = verify_transactions(firefly_response, sent)
        assert len(warnings) == 1
        assert "date mismatch" in warnings[0]
        assert "2019-04-15" in warnings[0]
        assert "2026-04-15" in warnings[0]

    def test_amount_mismatch_warning(self):
        firefly_response = {
            "data": {
                "created": [
                    {
                        "id": "1",
                        "transactions": [
                            {
                                "attributes": {
                                    "date": "2019-04-15",
                                    "amount": "99.99",
                                    "type": "withdrawal",
                                }
                            }
                        ],
                    }
                ]
            }
        }
        sent = [{"date": "2019-04-15", "amount": "49.99", "type": "withdrawal"}]
        warnings = verify_transactions(firefly_response, sent)
        assert len(warnings) == 1
        assert "amount mismatch" in warnings[0]

    def test_empty_response_no_warnings(self):
        firefly_response = {"data": {"created": []}}
        sent = [{"date": "2019-04-15", "amount": "49.99"}]
        warnings = verify_transactions(firefly_response, sent)
        assert warnings == []

    def test_multiple_mismatches(self):
        firefly_response = {
            "data": {
                "created": [
                    {
                        "id": "1",
                        "transactions": [
                            {
                                "attributes": {
                                    "date": "2026-01-01",
                                    "amount": "10.0",
                                    "type": "withdrawal",
                                }
                            },
                        ],
                    },
                    {
                        "id": "2",
                        "transactions": [
                            {
                                "attributes": {
                                    "date": "2026-01-02",
                                    "amount": "20.0",
                                    "type": "withdrawal",
                                }
                            },
                        ],
                    },
                ]
            }
        }
        sent = [
            {"date": "2019-01-01", "amount": "10.0", "type": "withdrawal"},
            {"date": "2019-01-02", "amount": "20.0", "type": "withdrawal"},
        ]
        warnings = verify_transactions(firefly_response, sent)
        assert len(warnings) == 2
        assert all("date mismatch" in w for w in warnings)


def _make_acct_tx(code, day="15", month="MAR", description="", depot=0.0, retrait=0.0, frais=0.0):
    return {
        "code": code,
        "date_day": day,
        "date_month": month,
        "description": description,
        "depot": depot,
        "retrait": retrait,
        "frais": frais,
    }


CHECKING_ID = 1
LOC_ID = 3
CC_PAYMENT_ID = 2


class TestMapAccountTransactions:
    def test_di_deposit(self):
        tx = [_make_acct_tx("DI", description="Paie / TESTCORP", depot=2222.33)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 0
        assert len(d) == 1
        assert len(t) == 0
        assert d[0]["type"] == "deposit"
        assert d[0]["amount"] == "2222.33"
        assert d[0]["destination_id"] == CHECKING_ID
        assert d[0]["source_name"] == "TESTCORP"

    def test_dcv_with_loc_is_transfer(self):
        tx = [_make_acct_tx("DCV", description="Dépôt provenant de marge de crédit", depot=44.44)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID, loc_account_id=LOC_ID)
        assert len(w) == 0
        assert len(t) == 0
        assert len(d) == 1
        assert d[0]["type"] == "deposit"
        assert d[0]["source_id"] == LOC_ID
        assert d[0]["destination_id"] == CHECKING_ID
        assert d[0]["amount"] == "44.44"

    def test_dcv_without_loc_is_deposit(self):
        tx = [_make_acct_tx("DCV", description="Dépôt provenant de marge de crédit", depot=44.44)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(t) == 0
        assert len(d) == 1
        assert d[0]["type"] == "deposit"
        assert d[0]["source_name"] == "marge de crédit"

    def test_vmw_deposit(self):
        tx = [_make_acct_tx("VMW", description="Dépôt - Virement Interac", depot=100.00)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 0
        assert len(d) == 1
        assert d[0]["type"] == "deposit"
        assert d[0]["amount"] == "100.0"

    def test_vmw_withdrawal(self):
        tx = [_make_acct_tx("VMW", description="Retrait - Virement Interac à: / Alex Martin", retrait=82.50)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 1
        assert len(d) == 0
        assert w[0]["type"] == "withdrawal"
        assert w[0]["amount"] == "82.5"
        assert w[0]["source_id"] == CHECKING_ID
        assert w[0]["destination_name"] == "interact-alex martin"

    def test_vap_with_loc_is_withdrawal(self):
        tx = [_make_acct_tx("VAP", description="Virement-remboursement / à MC 3", retrait=66.66)]
        w, d, t = map_account_transactions(
            tx,
            2019,
            CHECKING_ID,
            loc_account_id=LOC_ID,
            cc_account_id=CC_PAYMENT_ID,
        )
        assert len(t) == 0
        assert len(w) == 1
        assert w[0]["type"] == "withdrawal"
        assert w[0]["source_id"] == CHECKING_ID
        assert w[0]["destination_id"] == LOC_ID
        assert w[0]["amount"] == "66.66"

    def test_vap_without_loc_is_withdrawal(self):
        tx = [_make_acct_tx("VAP", description="Virement-remboursement / à MC 3", retrait=66.66)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID, cc_account_id=CC_PAYMENT_ID)
        assert len(t) == 0
        assert len(w) == 1
        assert w[0]["type"] == "withdrawal"
        assert w[0]["source_id"] == CHECKING_ID

    def test_ach_withdrawal(self):
        tx = [_make_acct_tx("ACH", description="Achat / SUPERMARCHE TEST", retrait=33.33)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 1
        assert w[0]["type"] == "withdrawal"
        assert w[0]["destination_name"] == "SUPERMARCHE TEST"

    def test_ra_transfer(self):
        tx = [_make_acct_tx("RA", description="Paiement / MC DESJARDINS 03/19", retrait=1444.22)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID, cc_account_id=CC_PAYMENT_ID)
        assert len(w) == 0
        assert len(t) == 1
        assert t[0]["type"] == "transfer"
        assert t[0]["source_id"] == CHECKING_ID
        assert t[0]["destination_id"] == CC_PAYMENT_ID
        assert t[0]["amount"] == "1444.22"

    def test_ra_non_cc_is_withdrawal(self):
        tx = [
            _make_acct_tx(
                "RA",
                description="Hypothèque / BANQUE GENERIQUE DU CANADA",
                retrait=888.44,
            )
        ]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID, cc_account_id=CC_PAYMENT_ID)
        assert len(w) == 1
        assert len(t) == 0
        assert w[0]["type"] == "withdrawal"
        assert w[0]["destination_name"] == "BANQUE GENERIQUE DU CANADA"

    def test_ra_mortgage_with_account_id(self):
        tx = [
            _make_acct_tx(
                "RA",
                description="Hypothèque / BANQUE GENERIQUE DU CANADA",
                retrait=888.44,
            )
        ]
        w, d, t = map_account_transactions(
            tx,
            2019,
            CHECKING_ID,
            cc_account_id=CC_PAYMENT_ID,
            mortgage_account_id=6,
        )
        assert len(w) == 1
        assert len(t) == 0
        assert w[0]["type"] == "withdrawal"
        assert w[0]["destination_id"] == 6
        assert w[0]["source_id"] == CHECKING_ID

    def test_ra_centre_prets_mortgage(self):
        tx = [
            _make_acct_tx(
                "RA",
                description="Paiement / CENTRE PRETS GENERIQUE",
                retrait=777.55,
            )
        ]
        w, d, t = map_account_transactions(
            tx,
            2019,
            CHECKING_ID,
            mortgage_account_id=6,
        )
        assert len(w) == 1
        assert w[0]["destination_id"] == 6

    def test_ra_regular_expense(self):
        tx = [
            _make_acct_tx(
                "RA",
                description="Électricité / ENERGIE PROVINCIALE",
                retrait=222.11,
            )
        ]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 1
        assert len(t) == 0
        assert w[0]["destination_name"] == "ENERGIE PROVINCIALE"

    def test_irga_withdrawal(self):
        tx = [
            _make_acct_tx(
                "IRGA",
                description="Retrait au GA / GA TEST CENTRE",
                retrait=111.11,
            )
        ]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 1
        assert w[0]["type"] == "withdrawal"
        assert w[0]["destination_name"] == "GA / GA TEST CENTRE"

    def test_apa_withdrawal(self):
        tx = [
            _make_acct_tx(
                "APA",
                description="Achat préautorisé / ENTREPOT ESSENCE W556",
                retrait=77.77,
            )
        ]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 1
        assert w[0]["type"] == "withdrawal"
        assert w[0]["destination_name"] == "ENTREPOT ESSENCE W556"

    def test_ddi_deposit(self):
        tx = [
            _make_acct_tx(
                "DDI",
                description="Paie / Testcorp inc.",
                depot=5555.44,
            )
        ]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(d) == 1
        assert d[0]["type"] == "deposit"
        assert d[0]["source_name"] == "Testcorp inc."

    def test_dmd_deposit(self):
        tx = [
            _make_acct_tx(
                "DMD",
                description="Dépôt Mobile",
                depot=333.33,
            )
        ]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(d) == 1
        assert d[0]["type"] == "deposit"
        assert d[0]["source_name"] == "Dépôt Mobile"

    def test_crm_deposit_refund(self):
        tx = [
            _make_acct_tx(
                "CRM",
                description="Retour paiement direct / PHARMACIE CENTRE",
                depot=55.55,
            )
        ]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(d) == 1
        assert d[0]["type"] == "deposit"
        assert d[0]["source_name"] == "PHARMACIE CENTRE"

    def test_xww_with_loc_is_withdrawal(self):
        tx = [
            _make_acct_tx(
                "XWW",
                description="Remboursement prêt -AccèsD Internet",
                retrait=5555.55,
            )
        ]
        w, d, t = map_account_transactions(
            tx,
            2019,
            CHECKING_ID,
            loc_account_id=LOC_ID,
            cc_account_id=CC_PAYMENT_ID,
        )
        assert len(t) == 0
        assert len(w) == 1
        assert w[0]["type"] == "withdrawal"
        assert w[0]["source_id"] == CHECKING_ID
        assert w[0]["destination_id"] == LOC_ID
        assert w[0]["amount"] == "5555.55"

    def test_xww_without_loc_is_withdrawal(self):
        tx = [
            _make_acct_tx(
                "XWW",
                description="Remboursement prêt -AccèsD Internet",
                retrait=5555.55,
            )
        ]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID, cc_account_id=CC_PAYMENT_ID)
        assert len(t) == 0
        assert len(w) == 1
        assert w[0]["type"] == "withdrawal"

    def test_iaga_withdrawal(self):
        tx = [_make_acct_tx("IAGA", description="Retrait au GA / GA / CD TESTZONE", retrait=444.44)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 1
        assert w[0]["type"] == "withdrawal"
        assert w[0]["amount"] == "444.44"

    def test_frais_creates_separate_withdrawal(self):
        tx = [_make_acct_tx("ACH", description="Achat / STORE", retrait=10.00, frais=1.50)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 2
        frais_tx = [x for x in w if x["description"] == "Frais bancaires"]
        assert len(frais_tx) == 1
        assert frais_tx[0]["amount"] == "1.5"
        assert frais_tx[0]["destination_name"] == "Caisses Desjardins"
        assert frais_tx[0]["source_id"] == CHECKING_ID

    def test_frais_zero_no_extra_withdrawal(self):
        tx = [_make_acct_tx("ACH", description="Achat / STORE", retrait=10.00, frais=0.0)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 1
        assert all(x["description"] != "Frais bancaires" for x in w)

    def test_date_formatting(self):
        tx = [_make_acct_tx("DI", day="7", month="MAR", description="Paie", depot=100.00)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert d[0]["date"] == "2019-03-07"

    def test_date_formatting_single_digit_day(self):
        tx = [_make_acct_tx("DI", day="1", month="JAN", description="Paie", depot=50.00)]
        w, d, t = map_account_transactions(tx, 2020, CHECKING_ID)
        assert d[0]["date"] == "2020-01-01"

    def test_three_way_split(self):
        transactions = [
            _make_acct_tx("DI", description="Paie", depot=1888.99),
            _make_acct_tx("DCV", description="Dépôt marge", depot=44.44),
            _make_acct_tx("ACH", description="Achat", retrait=33.33),
            _make_acct_tx("VAP", description="Virement MC", retrait=66.66),
            _make_acct_tx("RA", description="Paiement / MC DESJARDINS 03/19", retrait=1444.22),
            _make_acct_tx("XWW", description="Remboursement prêt", retrait=5555.55),
        ]
        w, d, t = map_account_transactions(
            transactions,
            2019,
            CHECKING_ID,
            cc_account_id=CC_PAYMENT_ID,
            loc_account_id=LOC_ID,
        )
        assert len(d) == 2
        assert len(w) == 3
        assert len(t) == 1

    def test_accepts_dataclass_transactions(self):
        from app.account_extractor import AccountTransaction

        tx = [
            AccountTransaction(
                date_day="15",
                date_month="MAR",
                code="DI",
                description="Paie",
                account_type="eop",
                depot=100.00,
            )
        ]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(d) == 1
        assert d[0]["type"] == "deposit"
        assert d[0]["amount"] == "100.0"

    def test_zero_amount_skipped(self):
        tx = [_make_acct_tx("ACH", description="Correction d'achat", retrait=0.0)]
        w, d, t = map_account_transactions(tx, 2019, CHECKING_ID)
        assert len(w) == 0
        assert len(d) == 0
        assert len(t) == 0

    def test_empty_transactions(self):
        w, d, t = map_account_transactions([], 2019, CHECKING_ID)
        assert w == []
        assert d == []
        assert t == []


class TestMapBonidollars:
    """Test bonidollars mapping functionality."""

    def test_accumulated_creates_deposit(self):
        """Bonidollars accumulated should create a deposit transaction."""
        deposits, withdrawals = map_bonidollars(
            accumulated=100.50,
            used=None,
            year=2024,
            month=12,
            day=19,
            cc_account_id=9,
        )

        assert len(deposits) == 1
        assert len(withdrawals) == 0

        deposit = deposits[0]
        assert deposit["type"] == "deposit"
        assert deposit["date"] == "2024-12-19"
        assert float(deposit["amount"]) == 100.50
        assert deposit["description"] == "Bonidollars accumulés"
        assert deposit["source_name"] == "Bonidollars accumulés"
        assert deposit["destination_id"] == 9

    def test_used_creates_withdrawal(self):
        """Bonidollars used should create a withdrawal transaction."""
        deposits, withdrawals = map_bonidollars(
            accumulated=None,
            used=50.25,
            year=2024,
            month=1,
            day=5,
            cc_account_id=9,
        )

        assert len(deposits) == 0
        assert len(withdrawals) == 1

        withdrawal = withdrawals[0]
        assert withdrawal["type"] == "withdrawal"
        assert withdrawal["date"] == "2024-01-05"
        assert withdrawal["amount"] == "50.25"
        assert withdrawal["description"] == "Bonidollars utilisés"
        assert withdrawal["source_id"] == 9
        assert withdrawal["destination_name"] == "Bonidollars utilisés"

    def test_both_accumulated_and_used(self):
        """Both accumulated and used should create both transactions."""
        deposits, withdrawals = map_bonidollars(
            accumulated=114.67,
            used=279.09,
            year=2024,
            month=12,
            day=19,
            cc_account_id=9,
        )

        assert len(deposits) == 1
        assert len(withdrawals) == 1

        assert deposits[0]["amount"] == "114.67"
        assert withdrawals[0]["amount"] == "279.09"

    def test_zero_accumulated_skipped(self):
        """Zero accumulated should not create a deposit."""
        deposits, withdrawals = map_bonidollars(
            accumulated=0.0,
            used=50.0,
            year=2024,
            month=12,
            day=19,
            cc_account_id=9,
        )

        assert len(deposits) == 0
        assert len(withdrawals) == 1

    def test_zero_used_skipped(self):
        """Zero used should not create a withdrawal."""
        deposits, withdrawals = map_bonidollars(
            accumulated=100.0,
            used=0.0,
            year=2024,
            month=12,
            day=19,
            cc_account_id=9,
        )

        assert len(deposits) == 1
        assert len(withdrawals) == 0

    def test_none_accumulated_and_used(self):
        """None values should result in empty lists."""
        deposits, withdrawals = map_bonidollars(
            accumulated=None,
            used=None,
            year=2024,
            month=12,
            day=19,
            cc_account_id=9,
        )

        assert len(deposits) == 0
        assert len(withdrawals) == 0

    def test_date_zero_padding(self):
        """Single digit month and day should be zero-padded."""
        deposits, withdrawals = map_bonidollars(
            accumulated=100.0,
            used=50.0,
            year=2024,
            month=1,
            day=5,
            cc_account_id=9,
        )

        assert deposits[0]["date"] == "2024-01-05"
        assert withdrawals[0]["date"] == "2024-01-05"
