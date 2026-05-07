"""Application configuration."""

import os
from dataclasses import dataclass
from pathlib import Path


def _find_dotenv() -> Path | None:
    candidates = [
        Path.cwd() / ".env",
        Path.home() / ".config" / "jardinier" / ".env",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _load_dotenv():
    env_path = _find_dotenv()
    if env_path is None:
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


@dataclass
class Config:
    api_url: str | None = None
    api_token: str | None = None
    cc_account_id: int | None = None
    checking_account_id: int | None = None
    expense_account_id: int | None = None
    loc_account_id: int | None = None
    mortgage_account_id: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    dry_run: bool = False

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            api_url=os.environ.get("FIREFLY_API_URL"),
            api_token=os.environ.get("FIREFLY_API_TOKEN"),
        )

    def validate_api(self):
        if not self.api_url:
            raise ValueError("FIREFLY_API_URL is not set. Set it via environment variable or .env file.")
        if not self.api_token:
            raise ValueError("FIREFLY_API_TOKEN is not set. Set it via environment variable or .env file.")
