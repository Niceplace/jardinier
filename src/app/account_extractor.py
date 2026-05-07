#!/usr/bin/env python3
"""
Account Statement Extractor for Desjardins Caisse Statements

Extracts transaction data from Desjardins account statements (relevé de compte).
Handles EOP COMPTE OFFRE EXCLUSIVE (checking) and MARGE DE CREDIT (line of credit) accounts.
Skips savings and registered accounts (REER, CELI, etc.).
"""

import re
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple
import pdfplumber


@dataclass
class AccountTransaction:
    date_day: str
    date_month: str
    code: str
    description: str
    account_type: str
    frais: float = 0.0
    retrait: float = 0.0
    depot: float = 0.0
    interet: float = 0.0
    avance: float = 0.0
    remboursement: float = 0.0
    solde: float = 0.0


@dataclass
class LocSummary:
    authorized_amount: float
    available_amount: float
    current_balance: float
    opening_balance: float = 0.0


@dataclass
class AccountExtractionResult:
    eop_transactions: List[AccountTransaction]
    loc_transactions: List[AccountTransaction]
    loc_summary: Optional[LocSummary]
    metadata: Dict[str, Any]


class AccountExtractor:
    EOP_HEADERS = [
        "COMPTE OFFRE EXCLUSIVE",
        "COMPTE A HAUT RENDEMENT DESJARDINS",
        "COMPTE À LA CARTE",
        "COMPTE A LA CARTE",
        "COMPTE D'OPÉRATIONS COURANTES",
        "COMPTE D'OPERATIONS COURANTES",
    ]
    LOC_HEADER = "MARGE DE CREDIT"

    EOP_WITHDRAWAL_CODES = {"ACH", "RA", "XWW", "IAGA", "IRGA", "APA", "VAP"}
    EOP_DEPOSIT_CODES = {"DI", "DCV", "DDI", "DMD", "IDGA", "IDSL", "CDI", "CRM"}
    LOC_AVANCE_CODES = {"DT"}
    LOC_REMBOURSEMENT_CODES = {"CT", "REC", "RIC"}

    MONTHS = {
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

    TRANSACTION_LINE_RE = re.compile(r"^(\d{1,2})\s+(" + "|".join(MONTHS.keys()) + r")\s+(\w{2,4})\s+(.+)$")

    AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\s\d{3})*\.\d{2})(-?)")

    SKIP_ACCOUNT_NAMES = [
        "COMPTE D'EPARGNE",
        "EPARGNE STABLE",
        "Compte d'\u00c9pargne",
        "Compte d'epargne",
        "PART DE QUALIFICATION",
    ]

    def __init__(self, pdf_path: str, start_date: str, end_date: str):
        self.pdf_path = Path(pdf_path)
        self.start_date = start_date
        self.end_date = end_date
        self.year = int(start_date[:4])

    def extract(self) -> AccountExtractionResult:
        with pdfplumber.open(self.pdf_path) as pdf:
            full_text = "\n".join(page.extract_text(layout=True) or "" for page in pdf.pages)

        lines = full_text.split("\n")

        eop_transactions: List[AccountTransaction] = []
        loc_transactions: List[AccountTransaction] = []
        loc_lines: List[str] = []

        current_section = None
        pending_eop_line: Optional[str] = None
        pending_loc_line: Optional[str] = None

        for line in lines:
            stripped = line.strip()

            if self._is_eop_header(stripped):
                current_section = "eop"
                pending_eop_line = None
                pending_loc_line = None
                continue

            if self._is_loc_header(stripped):
                current_section = "loc"
                loc_lines = []
                pending_eop_line = None
                pending_loc_line = None
                continue

            if self._is_skip_header(stripped):
                current_section = None
                pending_eop_line = None
                pending_loc_line = None
                continue

            if current_section == "eop":
                if self._is_continuation_line(stripped):
                    if pending_eop_line is not None:
                        pending_eop_line += " " + stripped
                    continue

                if pending_eop_line is not None:
                    tx = self._parse_eop_line(pending_eop_line)
                    if tx is not None:
                        eop_transactions.append(tx)
                    pending_eop_line = None

                tx = self._parse_eop_line(stripped)
                if tx is not None:
                    eop_transactions.append(tx)
                else:
                    pending_eop_line = stripped

            elif current_section == "loc":
                if self._is_loc_continuation_line(stripped):
                    if pending_loc_line is not None:
                        pending_loc_line += " " + stripped
                    continue

                if pending_loc_line is not None:
                    loc_lines.append(pending_loc_line)
                    tx = self._parse_loc_line(pending_loc_line)
                    if tx is not None:
                        loc_transactions.append(tx)
                    pending_loc_line = None

                loc_lines.append(stripped)
                tx = self._parse_loc_line(stripped)
                if tx is not None:
                    loc_transactions.append(tx)
                else:
                    pending_loc_line = stripped

        if pending_eop_line is not None:
            tx = self._parse_eop_line(pending_eop_line)
            if tx is not None:
                eop_transactions.append(tx)

        if pending_loc_line is not None:
            loc_lines.append(pending_loc_line)
            tx = self._parse_loc_line(pending_loc_line)
            if tx is not None:
                loc_transactions.append(tx)

        loc_summary = self._parse_loc_summary(loc_lines) if loc_lines else None

        metadata = {
            "pdf_path": str(self.pdf_path),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "year": self.year,
            "eop_count": len(eop_transactions),
            "loc_count": len(loc_transactions),
        }

        return AccountExtractionResult(
            eop_transactions=eop_transactions,
            loc_transactions=loc_transactions,
            loc_summary=loc_summary,
            metadata=metadata,
        )

    def _is_eop_header(self, line: str) -> bool:
        return any(h in line.upper() for h in self.EOP_HEADERS)

    def _is_loc_header(self, line: str) -> bool:
        return self.LOC_HEADER in line.upper()

    def _is_skip_header(self, line: str) -> bool:
        return any(name in line for name in self.SKIP_ACCOUNT_NAMES)

    def _is_continuation_line(self, line: str) -> bool:
        if not self.AMOUNT_RE.search(line):
            return False
        if self.TRANSACTION_LINE_RE.match(line):
            return False
        if "Solde reporté" in line:
            return False
        if "Montant" in line and ("autoris" in line.lower() or "disponible" in line.lower()):
            return False
        if re.match(r"^(MC|CS|ET|ES)\s+\d", line):
            return False
        if "Intérêts" in line and "exigibles" in line:
            return False
        if "Taux" in line and "crédit" in line.lower():
            return False
        if (
            line.startswith("AVIS")
            or line.startswith("LE TAUX")
            or line.startswith("TEL QUE")
            or line.startswith("POUR PLUS")
            or line.startswith("AVISER")
            or line.startswith("Veuillez")
        ):
            return False
        return True

    def _is_loc_continuation_line(self, line: str) -> bool:
        if not self.AMOUNT_RE.search(line):
            return False
        if self.TRANSACTION_LINE_RE.match(line):
            return False
        if "Solde reporté" in line:
            return False
        if "Montant" in line and ("autoris" in line.lower() or "disponible" in line.lower()):
            return False
        if re.match(r"^(MC|CS|ET|ES)\s+\d", line):
            return False
        if "Intérêts" in line and "exigibles" in line:
            return False
        if "Taux" in line and "crédit" in line.lower():
            return False
        return True

    def _extract_amounts_and_description(self, text: str, is_loc: bool = False) -> Tuple[str, List[float]]:
        amounts: List[Tuple[int, float]] = []
        first_match_start = len(text)

        for match in self.AMOUNT_RE.finditer(text):
            if is_loc:
                after = text[match.end() :].lstrip()
                if after.startswith("$"):
                    continue

            amount_str = match.group(1)
            is_negative = match.group(2) == "-"
            clean = amount_str.replace(" ", "")
            value = float(clean)
            if is_negative:
                value = -value

            amounts.append((match.start(), value))
            if len(amounts) == 1:
                first_match_start = match.start()

        description = text[:first_match_start].strip()
        return description, [a[1] for a in amounts]

    def _parse_eop_line(self, line: str) -> Optional[AccountTransaction]:
        if "Solde reporté" in line:
            return None

        match = self.TRANSACTION_LINE_RE.match(line)
        if not match:
            return None

        date_day = match.group(1)
        date_month = match.group(2)
        code = match.group(3)
        rest = match.group(4)

        description, amounts = self._extract_amounts_and_description(rest, is_loc=False)

        if not amounts:
            return None

        solde = amounts[-1]
        frais = 0.0
        retrait = 0.0
        depot = 0.0

        if len(amounts) == 2:
            value = amounts[0]
            if self._is_eop_deposit(code, description):
                depot = value
            else:
                retrait = value
        elif len(amounts) == 3:
            frais = amounts[0]
            value = amounts[1]
            if self._is_eop_deposit(code, description):
                depot = value
            else:
                retrait = value
        elif len(amounts) >= 4:
            frais = amounts[0]
            retrait = amounts[1]
            depot = amounts[2]

        return AccountTransaction(
            date_day=date_day,
            date_month=date_month,
            code=code,
            description=description,
            account_type="eop",
            frais=frais,
            retrait=retrait,
            depot=depot,
            solde=solde,
        )

    def _parse_loc_line(self, line: str) -> Optional[AccountTransaction]:
        if "Solde reporté" in line:
            return None

        match = self.TRANSACTION_LINE_RE.match(line)
        if not match:
            return None

        date_day = match.group(1)
        date_month = match.group(2)
        code = match.group(3)
        rest = match.group(4)

        description, amounts = self._extract_amounts_and_description(rest, is_loc=True)

        if not amounts:
            return None

        solde = amounts[-1]
        interet = 0.0
        avance = 0.0
        remboursement = 0.0

        if len(amounts) == 2:
            if code in self.LOC_AVANCE_CODES:
                avance = amounts[0]
            else:
                remboursement = amounts[0]
        elif len(amounts) == 3:
            interet = amounts[0]
            if code in self.LOC_AVANCE_CODES:
                avance = amounts[1]
            else:
                remboursement = amounts[1]
        elif len(amounts) >= 4:
            interet = amounts[0]
            avance = amounts[1]
            remboursement = amounts[2]

        return AccountTransaction(
            date_day=date_day,
            date_month=date_month,
            code=code,
            description=description,
            account_type="loc",
            interet=interet,
            avance=avance,
            remboursement=remboursement,
            solde=solde,
        )

    def _is_eop_deposit(self, code: str, description: str) -> bool:
        if code in self.EOP_DEPOSIT_CODES:
            return True
        if code == "VMW" and description.lower().startswith("d\u00e9p\u00f4t"):
            return True
        return False

    def _parse_loc_summary(self, lines: List[str]) -> Optional[LocSummary]:
        authorized = None
        available = None
        opening_balance = None

        for line in lines:
            if "Solde reporté" in line:
                match = re.search(r"Solde reporté\s+([\d\s]*\d\.\d{2})", line)
                if match:
                    opening_balance = self._parse_amount_value(match.group(1))

            auth_match = re.search(r"Montant autoris\u00e9\s*:\s*([\d\s]*\d\.\d{2})", line)
            if auth_match:
                authorized = self._parse_amount_value(auth_match.group(1))

            avail_match = re.search(r"Montant disponible\s*:\s*([\d\s]*\d\.\d{2})", line)
            if avail_match:
                available = self._parse_amount_value(avail_match.group(1))

        if authorized is not None and available is not None:
            current_balance = authorized - available
            return LocSummary(
                authorized_amount=authorized,
                available_amount=available,
                current_balance=current_balance,
                opening_balance=opening_balance or 0.0,
            )

        return None

    def _parse_amount_value(self, amount_str: str) -> float:
        clean = amount_str.replace(" ", "")
        return float(clean)

    def to_json(self, result: AccountExtractionResult) -> Dict[str, Any]:
        data = {
            "metadata": result.metadata,
            "eop_transactions": [asdict(t) for t in result.eop_transactions],
            "loc_transactions": [asdict(t) for t in result.loc_transactions],
        }
        if result.loc_summary:
            data["loc_summary"] = asdict(result.loc_summary)
        return data
