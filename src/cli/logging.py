"""Logging configuration for CLI."""

import logging
import sys
from pathlib import Path
from typing import Optional

DEFAULT_LOG_PATH = Path.home() / ".local" / "share" / "jardinier" / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_PATH / "jardinier.log"


def setup_logging(log_file: Optional[Path] = None, verbose: bool = False, json_output: bool = False) -> logging.Logger:
    """
    Configure logging to both file and console.

    Args:
        log_file: Path to log file (default: ~/.local/share/jardinier/logs/jardinier.log)
        verbose: Enable DEBUG level logging
        json_output: Disable pretty formatting for JSON mode
    """
    # Create logger
    logger = logging.getLogger("jardinier")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler
    if json_output:
        # JSON mode: no formatting, raw output to stdout
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        # Pretty mode: emojis and formatting to stderr
        console_handler = logging.StreamHandler(sys.stdout if json_output else sys.stderr)
        console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
        console_handler.setFormatter(CLIFormatter())

    logger.addHandler(console_handler)

    # File handler
    log_path = log_file or DEFAULT_LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(file_handler)

    return logger


class CLIFormatter(logging.Formatter):
    """Custom formatter with emojis."""

    def format(self, record):
        if record.levelno >= logging.ERROR:
            return f"✗ {record.getMessage()}"
        elif record.levelno == logging.WARNING:
            return f"⚠ {record.getMessage()}"
        else:
            return f"ℹ {record.getMessage()}"
