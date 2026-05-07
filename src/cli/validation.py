"""Account validation logic."""

import httpx
from typing import Tuple


def validate_account_id(
    account_id: int, api_url: str, api_token: str, timeout: float = 10.0
) -> Tuple[bool, str | None]:
    """
    Check if account ID exists in Firefly-III.

    Returns:
        (valid, error_message)
    """
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    }

    try:
        response = httpx.get(
            f"{api_url.rstrip('/')}/accounts/{account_id}",
            headers=headers,
            timeout=timeout,
        )

        if response.status_code == 200:
            return True, None
        elif response.status_code == 404:
            return False, f"Account ID {account_id} does not exist in Firefly-III"
        else:
            return (
                False,
                f"Failed to validate account ID {account_id}: HTTP {response.status_code}",
            )

    except httpx.TimeoutException:
        return False, f"Timeout validating account ID {account_id}"
    except httpx.RequestError as e:
        return False, f"Network error validating account ID {account_id}: {e}"
    except Exception as e:
        return False, f"Error validating account ID {account_id}: {e}"
