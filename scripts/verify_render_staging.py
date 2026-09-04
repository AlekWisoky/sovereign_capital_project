#!/usr/bin/env python3
"""Verify Render staging through read-only runtime endpoints."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

READ_ENDPOINTS = ("/health", "/api/deploy/info", "/api/state")


def get_json(base_url: str, path: str) -> Any:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "sovereign-capital-render-smoke/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise RuntimeError(f"{path}: HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{path}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{path}: connection failed: {exc.reason}") from exc


def _children(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return list(value.values())
    if isinstance(value, list):
        return value
    return []


def _find_key_values(value: Any, wanted: set[str]) -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            found.extend(
                (str(key), item)
                for key, item in current.items()
                if str(key).lower() in wanted
            )
        stack.extend(_children(current))
    return found


def main() -> int:
    base_url = (os.environ.get("RENDER_STAGING_URL") or "").strip()
    if not base_url:
        print("RENDER_STAGING_URL is required", file=sys.stderr)
        return 2

    print(f"Render staging: {base_url.rstrip('/')}")
    payloads: dict[str, Any] = {}
    for path in READ_ENDPOINTS:
        payloads[path] = get_json(base_url, path)
        print(f"PASS {path}")

    state = payloads["/api/state"]
    unsafe = [
        (key, value)
        for key, value in _find_key_values(state, {"auto_trading", "autotrading"})
        if value is True
    ]
    if unsafe:
        raise RuntimeError(f"staging reports auto trading enabled: {unsafe}")

    print("PASS staging safety: no auto-trading=true flag exposed")
    print("Render staging verification complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
