"""Date inference from filenames."""

import re
import calendar
from pathlib import Path
from typing import Optional, Tuple

# Patterns: 20240131.pdf or 2024-01-31.pdf
DATE_PATTERN = re.compile(r"(\d{4})[-._]?(\d{2})[-._]?(\d{2})")


DATE_WITH_DASHES_PATTERN = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def infer_dates_from_filename(filename: str) -> Optional[Tuple[str, str]]:
    """
    Infer statement start and end dates from filename.

    Examples:
        - 20240131.pdf → (2024-01-01, 2024-01-31)
        - 2024-01-31.pdf → (2024-01-01, 2024-01-31)
    """
    # Try to find date pattern
    match = DATE_PATTERN.search(filename)
    if not match:
        match = DATE_WITH_DASHES_PATTERN.search(filename)

    if not match:
        return None

    year, month, day = match.groups()

    # Calculate last day of month
    last_day = calendar.monthrange(int(year), int(month))[1]

    start_date = f"{year}-{month.zfill(2)}-01"
    end_date = f"{year}-{month.zfill(2)}-{str(last_day).zfill(2)}"

    return start_date, end_date


def infer_dates_for_pdf(pdf_path: Path) -> Tuple[str, str]:
    """
    Infer dates for a PDF file.

    Raises ValueError if inference fails.
    """
    filename = pdf_path.name

    # Try inference first
    dates = infer_dates_from_filename(filename)
    if dates:
        return dates

    # If inference fails, raise error with helpful message
    raise ValueError(
        f"Could not infer dates from filename '{filename}'. "
        "Please specify --start-date and --end-date explicitly, "
        "or rename file to match pattern: YYYYMMDD.pdf or YYYY-MM-DD.pdf"
    )
