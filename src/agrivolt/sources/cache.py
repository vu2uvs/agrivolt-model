"""A small on-disk cache for HTTP responses.

Upstream APIs are slow, rate limited, and occasionally down. Every source
module goes through `fetch_json` so that a scenario re-run costs nothing and
gives the same answer. Cache entries are keyed by a hash of the full request,
so changing any parameter naturally produces a new entry.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import requests

CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "cache"

DEFAULT_TIMEOUT = 120
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 3


class SourceUnavailable(RuntimeError):
    """Raised when an upstream source cannot be reached and nothing is cached."""


def _key(url: str, params: dict[str, Any]) -> str:
    canonical = url + "?" + json.dumps(params, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    label: str = "response",
    refresh: bool = False,
) -> dict[str, Any]:
    """GET `url` and return parsed JSON, reading from and writing to the cache.

    `label` only affects the cache filename; it exists so a human browsing
    `data/cache` can tell what is in there.
    """
    params = params or {}
    path = CACHE_DIR / f"{label}-{_key(url, params)}.json"

    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            break
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_SECONDS * attempt)
    else:
        raise SourceUnavailable(f"{url} failed after {MAX_ATTEMPTS} attempts") from last_error

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload
