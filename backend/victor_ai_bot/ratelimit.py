from __future__ import annotations

import os
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def _client_ip(request: Request) -> str:
    """Best-effort client IP.

    Safe default: use the direct socket peer (Starlette).
    If you run behind a trusted reverse proxy, set:
      VICTOR_TRUST_PROXY_HEADERS=1
    to respect X-Forwarded-For / X-Real-Ip.
    """
    trust = os.environ.get("VICTOR_TRUST_PROXY_HEADERS", "").strip() == "1"
    if trust:
        xff = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
        if xff:
            # left-most is the original client
            ip = xff.split(",")[0].strip()
            if ip:
                return ip
        xri = request.headers.get("x-real-ip") or request.headers.get("X-Real-Ip")
        if xri and xri.strip():
            return xri.strip()
    return request.client.host if request.client else "unknown"


@dataclass(frozen=True)
class _Rule:
    window_s: float
    max_requests: int


class _Limiter:
    """Bounded in-memory sliding-window rate limiter.

    Goals:
      - stop runaway polling or UI refresh loops
      - never grow memory unbounded
      - keep overhead tiny
    """

    def __init__(self, max_keys: int = 4096):
        self._max_keys = max_keys
        self._hits: "OrderedDict[str, Deque[float]]" = OrderedDict()

    def allow(self, key: str, rule: _Rule, now: float) -> bool:
        q = self._hits.get(key)
        if q is None:
            if len(self._hits) >= self._max_keys:
                # Drop oldest key to bound memory.
                self._hits.popitem(last=False)
            q = deque()
            self._hits[key] = q
        else:
            # Touch to keep LRU-ish.
            self._hits.move_to_end(key)

        cutoff = now - rule.window_s
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= rule.max_requests:
            return False
        q.append(now)
        return True


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple API rate limits for expensive endpoints.

    Defaults are intentionally permissive for local dev, but enough to prevent
    accidental DDOS from a client loop.

    Env overrides:
      - VICTOR_RL_HEAVY_MAX (default 12 per window)
      - VICTOR_RL_HEAVY_WINDOW_S (default 10s)
      - VICTOR_RL_LIGHT_MAX (default 90 per window)
      - VICTOR_RL_LIGHT_WINDOW_S (default 60s)
    """

    _heavy_paths = {
        "/api/opportunities/trade",
        "/api/tx/receipt",
        "/api/presets/apply",
    }
    _light_paths = {
        "/api/state",
        "/api/admin/state",
        "/api/pnl/summary",
        "/api/settings",
        "/api/safety",
    }

    def __init__(self, app):
        super().__init__(app)
        self._limiter = _Limiter(max_keys=_env_int("VICTOR_RL_MAX_KEYS", 4096))
        self._rule_heavy = _Rule(
            window_s=float(_env_int("VICTOR_RL_HEAVY_WINDOW_S", 10)),
            max_requests=_env_int("VICTOR_RL_HEAVY_MAX", 12),
        )
        self._rule_light = _Rule(
            window_s=float(_env_int("VICTOR_RL_LIGHT_WINDOW_S", 60)),
            max_requests=_env_int("VICTOR_RL_LIGHT_MAX", 90),
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        rule: Optional[_Rule] = None
        if path in self._heavy_paths:
            rule = self._rule_heavy
        elif path in self._light_paths:
            rule = self._rule_light
        if rule is None:
            return await call_next(request)

        ip = _client_ip(request)
        key = f"{ip}:{path}"
        now = time.monotonic()
        if not self._limiter.allow(key, rule, now):
            return JSONResponse(
                status_code=429,
                content={"ok": False, "error": "rate_limited", "path": path},
            )
        return await call_next(request)
