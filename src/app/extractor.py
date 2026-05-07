#!/usr/bin/env python3
"""
Transaction Extractor for MasterCard Statements

Extracts transaction data directly from PDF statements and validates against total amount.
"""

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pdfplumber


@dataclass
class Transaction:
    date_transaction_day: str
    date_transaction_month: str
    date_inscription_day: str
    date_inscription_month: str
    description: str
    city: str
    province: str
    bonidollars: str
    amount: float
    is_refund: bool
    foreign_currency: Optional[str] = None
    foreign_amount: Optional[float] = None
    exchange_rate: Optional[float] = None


@dataclass
class Cardholder:
    name: str
    card: str


@dataclass
class ExtractionResult:
    transactions: List[Transaction]
    previous_balance: float
    total_amount: float
    expected_change: float
    transaction_sum: float
    validation_passed: bool
    cardholders: List[Cardholder]
    metadata: Dict[str, Any]
    bonidollars_accumulated: Optional[float] = None
    bonidollars_used: Optional[float] = None


class Extractor:
    TRANSACTION_ANCHOR = "Transactions effectuées avec la carte de"
    TOTAL_ANCHOR = "Nouveau solde courant"
    PREVIOUS_BALANCE_ANCHOR = "Solde précédent"
    PROVINCES = [
        "QC",
        "ON",
        "MB",
        "BC",
        "AB",
        "SK",
        "NB",
        "NL",
        "PE",
        "NS",
        "YT",
        "NT",
        "NU",
        "PR",
    ]
    TOLERANCE = 10.00

    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)

    def extract(self) -> ExtractionResult:
        print(f"Extracting from: {self.pdf_path}")

        with pdfplumber.open(self.pdf_path) as pdf:
            cardholders = self._find_cardholders(pdf)
            previous_balance = self._find_amount(pdf, self.PREVIOUS_BALANCE_ANCHOR)
            total_amount = self._find_amount(pdf, self.TOTAL_ANCHOR)
            year = self._infer_statement_year(pdf)
            statement_date = self._extract_statement_date(pdf)
            bonidollars_accumulated, bonidollars_used = self._extract_bonidollars(pdf)

            if not cardholders:
                raise ValueError("FATAL: No transaction tables found in PDF")

            if previous_balance is None:
                raise ValueError("FATAL: Previous balance not found in PDF")

            if total_amount is None:
                raise ValueError("FATAL: Total amount not found in PDF")

            expected_change = total_amount - previous_balance

            transactions = []
            for page in pdf.pages:
                page_transactions = self._extract_from_page(page)
                transactions.extend(page_transactions)

        if year is None:
            from datetime import date

            year = date.today().year

        warnings = []
        for t in transactions:
            if abs(t.amount) > 10000.00:
                raise ValueError(
                    f"Transaction amount ${abs(t.amount):,.2f} exceeds $10,000 limit. Description: {t.description}"
                )
            if abs(t.amount) > 8000.00:
                warnings.append(f"WARNING: ${abs(t.amount):,.2f} - {t.description}")

        if warnings:
            for w in warnings:
                print(w)

        transaction_sum = sum(t.amount for t in transactions)
        validation_passed = abs(transaction_sum - expected_change) <= self.TOLERANCE

        cardholder_names = ", ".join(c.name for c in cardholders)
        print(f"Found {len(cardholders)} cardholder(s): {cardholder_names}")
        print(f"Previous balance: {previous_balance:,.2f}")
        print(f"Total amount: {total_amount:,.2f}")
        print(f"Expected change: {expected_change:,.2f}")
        print(f"Extracted {len(transactions)} transaction(s)")
        print(f"Transaction sum: {transaction_sum:,.2f}")

        if not validation_passed:
            difference = abs(transaction_sum - expected_change)
            print("FATAL: Transaction sum does not match expected change!")
            print(f"Difference: {difference:,.2f}")
            raise ValueError(
                f"Transaction sum ({transaction_sum:,.2f}) does not match "
                f"expected change ({expected_change:,.2f}). "
                f"Difference: {difference:,.2f}"
            )

        print("Validation PASSED")

        if bonidollars_accumulated is not None:
            print(f"Bonidollars accumulated: {bonidollars_accumulated:,.2f}")
        if bonidollars_used is not None:
            print(f"Bonidollars used: {bonidollars_used:,.2f}")

        metadata = {
            "pdf_path": str(self.pdf_path),
            "total_transactions": len(transactions),
            "previous_balance": previous_balance,
            "total_amount": total_amount,
            "expected_change": expected_change,
            "transaction_sum": transaction_sum,
            "validation_passed": validation_passed,
            "year": year,
            "statement_date": statement_date,
            "cardholders": [{"name": c.name, "card": c.card} for c in cardholders],
            "bonidollars_accumulated": bonidollars_accumulated,
            "bonidollars_used": bonidollars_used,
        }

        return ExtractionResult(
            transactions=transactions,
            previous_balance=previous_balance,
            total_amount=total_amount,
            expected_change=expected_change,
            transaction_sum=transaction_sum,
            validation_passed=validation_passed,
            cardholders=cardholders,
            metadata=metadata,
            bonidollars_accumulated=bonidollars_accumulated,
            bonidollars_used=bonidollars_used,
        )

    def _infer_statement_year(self, pdf) -> Optional[int]:
        month_names = [
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ]
        month_pattern = "(?:" + "|".join(month_names) + ")"
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            match = re.search(
                rf"\d{{1,2}}(?:er|ère|eme)?\s+{month_pattern}\s+(\d{{4}})\s+(?:au|à)\s+\d{{1,2}}(?:er|ère|eme)?\s+{month_pattern}\s+\d{{4}}",
                text,
            )
            if match:
                return int(match.group(1))
            match = re.search(
                rf"\d{{1,2}}(?:er|ère|eme)?\s+{month_pattern}\s+(?:au|à)\s+\d{{1,2}}(?:er|ère|eme)?\s+{month_pattern}\s+(\d{{4}})",
                text,
            )
            if match:
                return int(match.group(1))
        return None

    def _extract_statement_date(self, pdf) -> Optional[tuple[int, int, int]]:
        """Extract statement date from PDF.

        Returns:
            Tuple of (year, month, day) or None if not found.
        """
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            # Look for "DATE DU RELEVÉ Jour DD Mois MM Année YYYY"
            match = re.search(
                r"DATE DU RELEVÉ\s+Jour\s+(\d{1,2})\s+Mois\s+(\d{1,2})\s+Année\s+(\d{4})",
                text,
            )
            if match:
                day = int(match.group(1))
                month = int(match.group(2))
                year = int(match.group(3))
                return year, month, day

        return None

    def _find_cardholders(self, pdf) -> List[Cardholder]:
        cardholders = []
        cardholder_names = set()

        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            for i, line in enumerate(lines):
                # Find cardholder name from transaction anchor
                if self.TRANSACTION_ANCHOR in line:
                    match = re.search(rf"{re.escape(self.TRANSACTION_ANCHOR)}\s*:\s*(.+)", line)
                    if match:
                        cardholder_name = match.group(1).strip()

                        # Skip if already processed
                        if cardholder_name in cardholder_names:
                            continue

                        cardholder_names.add(cardholder_name)

                        # Look for card number in nearby lines (usually within 5 lines)
                        card_number = None
                        for j in range(max(0, i - 5), min(len(lines), i + 10)):
                            # Match card number pattern (4 groups of 4 digits)
                            card_match = re.search(r"(\d{4}\s+\d{4}\s+\d{4}\s+\d{4})", lines[j])
                            if card_match:
                                card_number = card_match.group(1)
                                break

                        # If no card found, use placeholder
                        if not card_number:
                            card_number = "XXXX XXXX XXXX XXXX"

                        cardholders.append(Cardholder(name=cardholder_name, card=card_number))

        return cardholders

    def _find_amount(self, pdf, anchor: str) -> Optional[float]:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            for i, line in enumerate(lines):
                if anchor in line:
                    for j in range(i, min(i + 5, len(lines))):
                        current_line = lines[j]
                        amounts = re.findall(r"[\d\s]+,\d{2}", current_line)
                        if amounts:
                            try:
                                clean_amount = amounts[0].replace(" ", "").replace(",", ".")
                                return float(clean_amount)
                            except ValueError:
                                continue

        return None

    def _extract_bonidollars(self, pdf) -> tuple[Optional[float], Optional[float]]:
        """Extract bonidollars accumulated and used from PDF.

        Returns:
            Tuple of (accumulated, used) amounts, or (None, None) if not found.
        """
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            for i, line in enumerate(lines):
                # Check for bonidollars section header (2024+ format)
                if "BONIDOLLARS ACCUMULÉS DEPUIS LE DERNIER RELEVÉ" in line:
                    # Look for amounts line in next 5 lines
                    for j in range(i + 1, min(i + 6, len(lines))):
                        amounts_line = lines[j].strip()

                        # Format: "606,06 + 114,67 - 279,09- + 0,00 = 441,64"
                        if "+" in amounts_line and "-" in amounts_line:
                            accumulated = None
                            used = None

                            # Extract accumulated (after first +)
                            acc_match = re.search(r"\+\s*([\d\s,]+)", amounts_line)
                            if acc_match:
                                try:
                                    accumulated = float(acc_match.group(1).replace(" ", "").replace(",", "."))
                                except ValueError:
                                    pass

                            # Extract used (after first -)
                            used_match = re.search(r"-\s*([\d\s,]+)-?", amounts_line)
                            if used_match:
                                try:
                                    used = float(used_match.group(1).replace(" ", "").replace(",", "."))
                                except ValueError:
                                    pass

                            if accumulated is not None and used is not None:
                                return accumulated, used

                # Check for older format (2019 and earlier)
                elif "BONIDOLLARS BONIDOLLARS" in line:
                    # Look for amounts line in next 5 lines
                    for j in range(i + 1, min(i + 6, len(lines))):
                        amounts_line = lines[j].strip()

                        # Format: "767,29 28,27 0,00 0,00 795,56"
                        # Columns: previous, accumulated, used, adjustments, new_balance
                        amounts = re.findall(r"[\d\s]+,\d{2}", amounts_line)
                        if len(amounts) >= 3:
                            try:
                                accumulated = float(amounts[1].replace(" ", "").replace(",", "."))
                                used = float(amounts[2].replace(" ", "").replace(",", "."))
                                return accumulated, used
                            except (ValueError, IndexError):
                                pass

        return None, None

    def _extract_from_page(self, page) -> List[Transaction]:
        text = page.extract_text()
        if not text:
            return []

        lines = text.split("\n")
        transactions = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            transaction_match = re.match(r"^(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(.+)$", line)

            if transaction_match:
                transaction = self._parse_transaction_line(transaction_match)

                if transaction:
                    transactions.append(transaction)

                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        foreign_match = re.search(r"([\d,]+)\s+(EUR|USD|GBP|EURO)\s+TX:\s*([\d.]+)", next_line)
                        if foreign_match:
                            transaction.foreign_amount = float(foreign_match.group(1).replace(",", "."))
                            currency = foreign_match.group(2)
                            transaction.foreign_currency = "EUR" if currency == "EURO" else currency
                            transaction.exchange_rate = float(foreign_match.group(3))
                            i += 1

            i += 1

        return transactions

    def _parse_transaction_line(self, match: re.Match) -> Optional[Transaction]:
        try:
            date_trans_day = match.group(1)
            date_trans_month = match.group(2)
            date_ins_day = match.group(3)
            date_ins_month = match.group(4)
            rest = match.group(5)

            parsed = self._parse_transaction_rest(rest)
            if not parsed:
                return None

            return Transaction(
                date_transaction_day=date_trans_day,
                date_transaction_month=date_trans_month,
                date_inscription_day=date_ins_day,
                date_inscription_month=date_ins_month,
                description=parsed["business"],
                city=parsed["city"],
                province=parsed["province"],
                bonidollars=parsed["bonidollars"],
                amount=parsed["amount"],
                is_refund=parsed["is_refund"],
                foreign_currency=None,
                foreign_amount=None,
                exchange_rate=None,
            )
        except Exception:
            return None

    def _parse_transaction_rest(self, rest: str) -> Optional[Dict[str, Any]]:
        if not rest:
            return None

        is_refund = bool(re.search(r"CR\s*$", rest))

        bonidollars = ""
        amount = 0.0

        boni_match = re.search(r"([\d,]+\s*%)", rest)
        if boni_match:
            bonidollars = boni_match.group(1)
            rest_after_boni = rest[boni_match.end() :].strip()

            amount_match = re.search(r"([\d\s,]+)$", rest_after_boni)
            if amount_match:
                try:
                    amount_str = amount_match.group(1).replace(" ", "").replace(",", ".")
                    amount = float(amount_str)
                except ValueError:
                    pass

            desc_part = rest[: boni_match.start()].strip()
        else:
            if is_refund:
                amount_match = re.search(r"([\d\s,]+)\s*CR", rest)
            else:
                amount_match = re.search(r"([\d\s,]+)\s*$", rest)

            if amount_match:
                try:
                    amount_str = amount_match.group(1).replace(" ", "").replace(",", ".")
                    amount = float(amount_str)
                except ValueError:
                    pass
                desc_part = rest[: amount_match.start()].strip()
            else:
                desc_part = rest

        if is_refund:
            amount = -amount

        parsed_desc = self._parse_description(desc_part)

        return {
            "business": parsed_desc["business"],
            "city": parsed_desc["city"],
            "province": parsed_desc["province"],
            "bonidollars": bonidollars,
            "amount": amount,
            "is_refund": is_refund,
        }

    def _parse_description(self, desc_line: str) -> Dict[str, Any]:
        result = {"business": "", "city": "", "province": ""}

        if not desc_line:
            return result

        parts = desc_line.split()

        for i, part in enumerate(parts):
            if part.upper() in self.PROVINCES:
                result["province"] = part.upper()
                business_parts = parts[:i]
                if len(business_parts) >= 1:
                    result["city"] = business_parts[-1] if len(business_parts) >= 1 else ""
                    result["business"] = " ".join(business_parts[:-1]) if len(business_parts) > 1 else ""
                break
        else:
            result["business"] = desc_line

        return result

    def to_json(self, result: ExtractionResult) -> Dict[str, Any]:
        return {
            "metadata": result.metadata,
            "transactions": [asdict(t) for t in result.transactions],
        }
