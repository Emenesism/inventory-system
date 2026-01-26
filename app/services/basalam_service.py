from __future__ import annotations

from typing import Any

import requests


def list_vendor_orders(
    vendor_id: str,
    base_url: str = "https://order-processing.basalam.com/v2/vendors",
    tab: str | None = None,
    start_paid_at: str | None = None,
    end_paid_at: str | None = None,
    limit: int = 10,
    offset: int = 0,
    access_token: str | None = None,
) -> dict[str, Any]:
    url = f"{base_url}/{vendor_id}/orders"
    params = {
        "tab": tab,
        "start_paid_at": start_paid_at,
        "end_paid_at": end_paid_at,
        "limit": limit,
        "offset": offset,
    }

    params = {k: v for k, v in params.items() if v is not None}

    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()
