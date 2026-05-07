"""Output formatting for CLI."""

import json
import sys
from typing import Any


class OutputFormatter:
    """Format CLI output as pretty text or JSON."""

    def __init__(self, json_output: bool = False, verbose: bool = False):
        self.json_output = json_output
        self._verbose = verbose

    def info(self, message: str):
        """Print info message."""
        if self.json_output:
            print(json.dumps({"level": "info", "message": message}))
        else:
            print(f"ℹ {message}")

    def success(self, message: str):
        """Print success message."""
        if self.json_output:
            print(json.dumps({"level": "success", "message": message}))
        else:
            print(f"✓ {message}")

    def error(self, message: str):
        """Print error message."""
        if self.json_output:
            print(json.dumps({"level": "error", "message": message}))
        else:
            print(f"✗ {message}", file=sys.stderr)

    def warning(self, message: str):
        """Print warning message."""
        if self.json_output:
            print(json.dumps({"level": "warning", "message": message}))
        else:
            print(f"⚠ {message}", file=sys.stderr)

    def verbose(self, message: str):
        """Print verbose message."""
        if self._verbose:
            if self.json_output:
                print(json.dumps({"level": "debug", "message": message}))
            else:
                print(f"  → {message}")

    def result(self, data: Any):
        """Print result (either pretty or JSON)."""
        if self.json_output:
            print(json.dumps(data, indent=2, default=str))
        else:
            self._pretty_print(data)

    def _pretty_print(self, data: Any):
        """Pretty print data structure."""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (list, dict)):
                    print(f"\n{key}:")
                    self._pretty_print(value)
                else:
                    print(f"  {key}: {value}")
        elif isinstance(data, list):
            for i, item in enumerate(data, 1):
                print(f"\n[{i}]")
                self._pretty_print(item)
        else:
            print(f"  {data}")
