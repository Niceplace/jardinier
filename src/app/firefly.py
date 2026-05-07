#!/usr/bin/env python3
"""
Firefly-III API client and transaction mapper.

Maps extracted Desjardins credit card and account statement transactions
to Firefly-III format and sends them via the API.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

import truststore

truststore.inject_into_ssl()

import httpx  # noqa: E402

CC_PAYMENT_PATTERNS = [
    r"PAIEMENT\s+AUTORISÉ",
    r"PRÉLÈVEMENT\s+EFFECTUÉ",
    r"PMT\s+WEB",
    r"PAYMENT\s+AUTHORIZED",
]


class FireflyClientError(Exception):
    pass


def _clean_merchant_name(description: str) -> str:
    description = re.sub(r"^\d{3}\s+", "", description)
    return description.strip()


ACCT_DESC_PREFIX_RE = re.compile(
    r"^[\wÀ-ÿ][\wÀ-ÿ'-]*"
    r"(?:\s+[\wÀ-ÿ][\wÀ-ÿ'-]*)*?"
    r"\s*(?:[/\-]\s*|(?:au|à|a|de|des|du|en|sur)\s+)",
    re.IGNORECASE,
)


def _clean_acct_merchant_name(description: str) -> str:
    cleaned = ACCT_DESC_PREFIX_RE.sub("", description).strip()
    while cleaned.startswith("/"):
        cleaned = cleaned[1:].strip()
    while cleaned.endswith("/"):
        cleaned = cleaned[:-1].strip()

    if "virement interac" in description.lower():
        parts = [p.strip() for p in description.split("/")]
        parts = [p for p in parts if p]
        if len(parts) >= 3:
            account_name = parts[-2].lower()
        else:
            account_name = parts[-1].lower() if parts else description.lower()
        cleaned = f"interact-{account_name}"

    return cleaned


def _is_cc_payment(description: str) -> bool:
    description_upper = description.upper()
    return any(re.search(pattern, description_upper) for pattern in CC_PAYMENT_PATTERNS)


def map_transactions(
    transactions: List[Dict[str, Any]],
    year: int,
    cc_account_id: int,
    expense_account_id: Optional[int] = None,
    checking_account_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Map Desjardins transactions to Firefly-III format.

    Returns (withdrawals, deposits, transfers) lists of Firefly transaction dicts.
    """
    withdrawals = []
    deposits = []
    transfers = []

    for txn in transactions:
        is_refund = txn.get("is_refund", False)
        description = txn["description"]
        raw_amount = abs(txn["amount"])
        if raw_amount == 0:
            continue
        amount = str(raw_amount)
        day = txn["date_transaction_day"].zfill(2)
        month = txn["date_transaction_month"].zfill(2)
        txn_date = f"{year}-{month}-{day}"

        location_parts = [txn.get("city", ""), txn.get("province", "")]
        notes = ", ".join(p for p in location_parts if p) or None

        firefly_txn: Dict[str, Any] = {
            "date": txn_date,
            "amount": amount,
            "description": _clean_merchant_name(description),
            "notes": notes,
        }

        if txn.get("foreign_currency"):
            firefly_txn["foreign_currency_code"] = txn["foreign_currency"]
        if txn.get("foreign_amount") is not None:
            firefly_txn["foreign_amount"] = str(abs(txn["foreign_amount"]))

        if _is_cc_payment(description):
            if checking_account_id is None:
                continue
            firefly_txn["type"] = "transfer"
            firefly_txn["source_id"] = checking_account_id
            firefly_txn["destination_id"] = cc_account_id
            transfers.append(firefly_txn)
        elif is_refund:
            firefly_txn["type"] = "deposit"
            firefly_txn["source_name"] = _clean_merchant_name(description)
            firefly_txn["destination_id"] = cc_account_id
            deposits.append(firefly_txn)
        else:
            firefly_txn["type"] = "withdrawal"
            firefly_txn["source_id"] = cc_account_id
            if expense_account_id is not None:
                firefly_txn["destination_id"] = expense_account_id
            else:
                firefly_txn["destination_name"] = _clean_merchant_name(description)
            withdrawals.append(firefly_txn)

    return withdrawals, deposits, transfers


def map_bonidollars(
    accumulated: Optional[float],
    used: Optional[float],
    year: int,
    month: int,
    day: int,
    cc_account_id: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Map bonidollars to Firefly-III transactions.

    Args:
        accumulated: Bonidollars accumulated (earned) amount
        used: Bonidollars used (spent) amount
        year: Statement year
        month: Statement month
        day: Statement day
        cc_account_id: Credit card account ID

    Returns:
        Tuple of (deposits, withdrawals) for bonidollars transactions
    """
    deposits = []
    withdrawals = []

    txn_date = f"{year}-{str(month).zfill(2)}-{str(day).zfill(2)}"

    # Bonidollars accumulated = revenue (deposit to CC)
    if accumulated and accumulated > 0:
        deposits.append(
            {
                "type": "deposit",
                "date": txn_date,
                "amount": str(accumulated),
                "description": "Bonidollars accumulés",
                "source_name": "Bonidollars accumulés",
                "destination_id": cc_account_id,
            }
        )

    # Bonidollars used = expense (withdrawal from CC)
    if used and used > 0:
        withdrawals.append(
            {
                "type": "withdrawal",
                "date": txn_date,
                "amount": str(used),
                "description": "Bonidollars utilisés",
                "source_id": cc_account_id,
                "destination_name": "Bonidollars utilisés",
            }
        )

    return deposits, withdrawals


EOP_DEPOSIT_CODES = {"DI", "DCV", "DDI", "DMD", "IDGA", "IDSL", "CDI", "CRM"}
EOP_LOC_TRANSFER_CODES = {"VAP", "XWW"}
MONTH_MAP = {
    "JAN": "01",
    "FEV": "02",
    "MAR": "03",
    "AVR": "04",
    "MAI": "05",
    "JUN": "06",
    "JUL": "07",
    "AOU": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}


def map_account_transactions(
    eop_transactions: List[Any],
    year: int,
    checking_account_id: int,
    cc_account_id: Optional[int] = None,
    loc_account_id: Optional[int] = None,
    mortgage_account_id: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Map Desjardins account statement EOP transactions to Firefly-III format.

    Returns (withdrawals, deposits, transfers) lists of Firefly transaction dicts.
    LoC transactions are skipped since they mirror EOP transactions.
    """
    withdrawals = []
    deposits = []
    transfers = []

    for tx in eop_transactions:
        if isinstance(tx, dict):
            code = tx["code"]
            day = str(tx["date_day"]).zfill(2)
            month = MONTH_MAP.get(tx["date_month"], tx["date_month"].zfill(2))
            description = tx["description"]
            depot = tx.get("depot", 0.0) or 0.0
            retrait = tx.get("retrait", 0.0) or 0.0
            frais = tx.get("frais", 0.0) or 0.0
        else:
            code = tx.code
            day = str(tx.date_day).zfill(2)
            month = MONTH_MAP.get(tx.date_month, tx.date_month.zfill(2))
            description = tx.description
            depot = tx.depot or 0.0
            retrait = tx.retrait or 0.0
            frais = tx.frais or 0.0

        txn_date = f"{year}-{month}-{day}"

        if frais > 0:
            withdrawals.append(
                {
                    "type": "withdrawal",
                    "date": txn_date,
                    "amount": str(abs(frais)),
                    "description": "Frais bancaires",
                    "source_id": checking_account_id,
                    "destination_name": "Caisses Desjardins",
                }
            )

        if code in EOP_DEPOSIT_CODES:
            amount = str(abs(depot))
            firefly_txn: Dict[str, Any] = {
                "type": "deposit",
                "date": txn_date,
                "amount": amount,
                "description": description,
                "source_name": _clean_acct_merchant_name(description),
                "destination_id": checking_account_id,
            }

            if code == "DCV" and loc_account_id is not None:
                firefly_txn["source_id"] = loc_account_id
                firefly_txn.pop("source_name")
                deposits.append(firefly_txn)
            else:
                deposits.append(firefly_txn)

        elif code == "VMW":
            if depot > 0:
                deposits.append(
                    {
                        "type": "deposit",
                        "date": txn_date,
                        "amount": str(abs(depot)),
                        "description": description,
                        "source_name": _clean_acct_merchant_name(description),
                        "destination_id": checking_account_id,
                    }
                )
            else:
                withdrawals.append(
                    {
                        "type": "withdrawal",
                        "date": txn_date,
                        "amount": str(abs(retrait)),
                        "description": description,
                        "source_id": checking_account_id,
                        "destination_name": _clean_acct_merchant_name(description),
                    }
                )

        elif code in EOP_LOC_TRANSFER_CODES:
            amount = str(abs(retrait))
            firefly_txn = {
                "date": txn_date,
                "amount": amount,
                "description": description,
            }

            if loc_account_id is not None:
                firefly_txn["type"] = "withdrawal"
                firefly_txn["source_id"] = checking_account_id
                firefly_txn["destination_id"] = loc_account_id
                withdrawals.append(firefly_txn)
            else:
                firefly_txn["type"] = "withdrawal"
                firefly_txn["source_id"] = checking_account_id
                firefly_txn["destination_name"] = _clean_acct_merchant_name(description)
                withdrawals.append(firefly_txn)

        elif code == "RA":
            amount = str(abs(retrait))
            desc_upper = description.upper()

            if "MC DESJARDINS" in desc_upper and cc_account_id is not None:
                firefly_txn = {
                    "type": "transfer",
                    "date": txn_date,
                    "amount": amount,
                    "description": description,
                    "source_id": checking_account_id,
                    "destination_id": cc_account_id,
                }
                transfers.append(firefly_txn)
            elif (
                "HYPOTHÈQUE" in desc_upper or "HYPOTHEQUE" in desc_upper or "CENTRE PRETS" in desc_upper
            ) and mortgage_account_id is not None:
                firefly_txn = {
                    "type": "withdrawal",
                    "date": txn_date,
                    "amount": amount,
                    "description": description,
                    "source_id": checking_account_id,
                    "destination_id": mortgage_account_id,
                }
                withdrawals.append(firefly_txn)
            else:
                firefly_txn = {
                    "type": "withdrawal",
                    "date": txn_date,
                    "amount": amount,
                    "description": description,
                    "source_id": checking_account_id,
                    "destination_name": _clean_acct_merchant_name(description),
                }
                withdrawals.append(firefly_txn)

        elif retrait > 0 or depot == 0:
            amount = abs(retrait) if retrait > 0 else abs(depot)
            if amount == 0:
                continue
            firefly_txn = {
                "type": "withdrawal",
                "date": txn_date,
                "amount": str(amount),
                "description": description,
                "source_id": checking_account_id,
                "destination_name": _clean_acct_merchant_name(description),
            }
            withdrawals.append(firefly_txn)

    return withdrawals, deposits, transfers


def fetch_asset_accounts(
    api_url: Optional[str] = None,
    api_token: Optional[str] = None,
    timeout: float = 30.0,
) -> List[Dict[str, Any]]:
    if not api_url:
        raise FireflyClientError("FIREFLY_API_URL is not configured")
    if not api_token:
        raise FireflyClientError("FIREFLY_API_TOKEN is not configured")

    base_url = api_url.rstrip("/")
    url = f"{base_url}/accounts?type=asset"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.get(url, headers=headers)

    if response.status_code != 200:
        raise FireflyClientError(f"Failed to fetch accounts: {response.status_code} {response.text}")

    data = response.json()
    accounts = []
    for item in data.get("data", []):
        attributes = item.get("attributes", {})
        accounts.append(
            {
                "id": int(item["id"]),
                "name": attributes.get("name", ""),
                "type": attributes.get("type", ""),
            }
        )
    return accounts


def build_batch(
    transactions: List[Dict[str, Any]],
    group_title: str,
    apply_rules: bool = False,
) -> Dict[str, Any]:
    return {
        "apply_rules": apply_rules,
        "group_title": group_title,
        "transactions": transactions,
    }


def send_batch(
    batch: Dict[str, Any],
    api_url: Optional[str] = None,
    api_token: Optional[str] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    if not api_url:
        raise FireflyClientError("FIREFLY_API_URL is not configured")
    if not api_token:
        raise FireflyClientError("FIREFLY_API_TOKEN is not configured")

    base_url = api_url.rstrip("/")
    token = api_token

    url = f"{base_url}/transactions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=batch, headers=headers)

    if response.status_code not in (200, 201):
        raise FireflyClientError(f"Firefly-III API returned {response.status_code}: {response.text}")

    return response.json()


def _destroy_objects(
    objects: str,
    api_url: Optional[str] = None,
    api_token: Optional[str] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    if not api_url:
        raise FireflyClientError("FIREFLY_API_URL is not configured")
    if not api_token:
        raise FireflyClientError("FIREFLY_API_TOKEN is not configured")

    base_url = api_url.rstrip("/")
    token = api_token

    url = f"{base_url}/data/destroy?objects={objects}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.delete(url, headers=headers)

    if response.status_code not in (200, 204):
        raise FireflyClientError(f"Firefly-III destroy endpoint returned {response.status_code}: {response.text}")

    return {"status": "success", "objects": objects}


def clear_all_transactions(
    api_url: Optional[str] = None,
    api_token: Optional[str] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    return _destroy_objects("transactions", api_url, api_token, timeout)


def clear_expense_accounts(
    api_url: Optional[str] = None,
    api_token: Optional[str] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    return _destroy_objects("expense_accounts", api_url, api_token, timeout)


def clear_revenue_accounts(
    api_url: Optional[str] = None,
    api_token: Optional[str] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    return _destroy_objects("revenue_accounts", api_url, api_token, timeout)


def verify_transactions(
    firefly_response: Dict[str, Any],
    sent_transactions: List[Dict[str, Any]],
) -> List[str]:
    warnings = []
    response_data = firefly_response.get("data", {})

    created_groups = []
    if isinstance(response_data, dict):
        created = response_data.get("created", [])
        if isinstance(created, list):
            created_groups = created
        elif isinstance(created, str):
            created_groups = [created]

    for i, group in enumerate(created_groups):
        group_id = group if isinstance(group, str) else group.get("id")
        transactions = group.get("transactions", []) if isinstance(group, dict) else []

        for j, txn in enumerate(transactions):
            attributes = txn.get("attributes", txn)
            expected = sent_transactions[i] if i < len(sent_transactions) else None
            if not expected:
                continue

            expected_date = expected.get("date", "")
            expected_amount = expected.get("amount", "")
            expected_type = expected.get("type", "")

            actual_date = str(attributes.get("date", ""))
            actual_amount = str(attributes.get("amount", ""))
            actual_type = str(attributes.get("type", ""))

            if actual_date and expected_date and actual_date != expected_date:
                warnings.append(
                    f"[WARNING] Transaction date mismatch: expected {expected_date}, "
                    f"got {actual_date} (group {group_id})"
                )
            if actual_amount and expected_amount and actual_amount != expected_amount:
                warnings.append(
                    f"[WARNING] Transaction amount mismatch: expected {expected_amount}, "
                    f"got {actual_amount} (group {group_id})"
                )
            if actual_type and expected_type and actual_type != expected_type:
                warnings.append(
                    f"[WARNING] Transaction type mismatch: expected {expected_type}, "
                    f"got {actual_type} (group {group_id})"
                )

    return warnings
