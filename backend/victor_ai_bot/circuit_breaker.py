from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class CircuitBreakerConfig:
    # Disable auto-trading after this many consecutive *failed* executions.
    max_consecutive_failures: int = 5
    # Disable auto-trading after this many consecutive on-chain reverts.
    max_consecutive_reverts: int = 3
    # Cooldown period after tripping.
    cooldown_s: int = 60


class CircuitBreaker:
    """Simple execution circuit breaker.

    Keeps the bot responsive and prevents runaway loss/fee burn when something
    breaks (RPC issues, calldata bugs, bad market regime).

    NOTE: We do *not* attempt to model drawdown in this baseline because the
    system does not currently track realized *losses* (only profits and
    success/failure). This trips on failure/revert streaks only.
    """

    def __init__(self, cfg: CircuitBreakerConfig):
        self.cfg = cfg
        self._consecutive_failures = 0
        self._consecutive_reverts = 0
        self._disabled_until: float = 0.0

    @staticmethod
    def from_env() -> "CircuitBreaker":
        def _i(name: str, d: int) -> int:
            try:
                return int(os.environ.get(name, str(d)))
            except (TypeError, ValueError):
                return d

        return CircuitBreaker(
            CircuitBreakerConfig(
                max_consecutive_failures=_i("VICTOR_CB_MAX_FAILURES", 5),
                max_consecutive_reverts=_i("VICTOR_CB_MAX_REVERTS", 3),
                cooldown_s=_i("VICTOR_CB_COOLDOWN_S", 60),
            )
        )

    def is_tripped(self) -> bool:
        return time.time() < self._disabled_until

    def remaining_cooldown_s(self) -> int:
        return max(0, int(self._disabled_until - time.time()))

    def allow_auto_trading(self) -> bool:
        return not self.is_tripped()

    def record_result(self, *, ok: bool, reason: Optional[str] = None) -> None:
        if ok:
            self._consecutive_failures = 0
            self._consecutive_reverts = 0
            return

        self._consecutive_failures += 1
        if reason and ("revert" in reason or "simulation" in reason):
            self._consecutive_reverts += 1

        if (
            self._consecutive_failures >= self.cfg.max_consecutive_failures
            or self._consecutive_reverts >= self.cfg.max_consecutive_reverts
        ):
            self._disabled_until = time.time() + float(self.cfg.cooldown_s)

    def snapshot(self) -> dict:
        return {
            "max_consecutive_failures": self.cfg.max_consecutive_failures,
            "max_consecutive_reverts": self.cfg.max_consecutive_reverts,
            "cooldown_s": self.cfg.cooldown_s,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_reverts": self._consecutive_reverts,
            "tripped": self.is_tripped(),
            "remaining_cooldown_s": self.remaining_cooldown_s(),
        }
