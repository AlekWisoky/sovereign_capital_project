from __future__ import annotations

import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque

from .persistence.repositories.bankroll_repository import BankrollEventRepository
from .persistence.repositories.capital_event_repository import CapitalEventRepository


_SAFE_BANKROLL_WINDOW_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_BANKROLL_OVERRIDE_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_BANKROLL_STATE_IO_EXCEPTIONS = (OSError, TypeError, ValueError)


@dataclass
class BankrollConfig:
    auto_reinvest_enabled: bool = False
    reinvest_rate_pct: int = 0
    max_borrow_amount_wei: int = 0
    base_borrow_amount_wei: int = 0
    kelly_enabled: bool = False
    kelly_window: int = 50
    kelly_min_history: int = 20
    kelly_cap_fraction: float = 0.75
    kelly_min_fraction: float = 0.05
    volatility_downscale: float = 0.35


@dataclass
class BankrollState:
    # Canonical signed economics. This may move below zero after a real loss.
    realized_profit_wei: int = 0
    realized_net_pnl_wei: int = 0
    bankroll_loss_wei: int = 0
    reinvestable_profit_wei: int = 0
    reinvested_profit_wei: int = 0
    cumulative_owned_capital_delta_wei: int = 0
    # Borrowed principal is tracked independently and is never profit.
    last_flashloan_principal_wei: int = 0
    last_flashloan_fee_wei: int = 0
    last_amount_in_wei: int = 0
    success_streak: int = 0
    fail_streak: int = 0
    updated_ts_ms: int = 0
    profit_updated_ts_ms: int = 0
    sizing_updated_ts_ms: int = 0
    recent_results: Deque[int] = field(default_factory=lambda: deque(maxlen=50))
    recent_returns: Deque[float] = field(default_factory=lambda: deque(maxlen=50))


class BankrollManager:
    def __init__(
        self,
        cfg: BankrollConfig,
        *,
        state_path: str | None = None,
        history_repo: BankrollEventRepository | None = None,
        capital_event_repo: CapitalEventRepository | None = None,
    ):
        self.cfg = cfg
        self._state_path = str(state_path or "")
        self._history_repo = history_repo
        self._capital_event_repo = capital_event_repo
        self.state = self._load_state()
        try:
            self._apply_configured_window()
        except _SAFE_BANKROLL_WINDOW_EXCEPTIONS:
            pass
        self._save_state()
        self._ensure_history_bootstrap()

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def _default_state(self) -> BankrollState:
        now_ms = self._now_ms()
        return BankrollState(
            updated_ts_ms=now_ms,
            profit_updated_ts_ms=now_ms,
            sizing_updated_ts_ms=now_ms,
        )

    def _state_payload(self) -> dict[str, Any]:
        return {
            "realized_profit_wei": int(self.state.realized_profit_wei),
            "realized_net_pnl_wei": int(self.state.realized_net_pnl_wei),
            "bankroll_loss_wei": int(self.state.bankroll_loss_wei),
            "reinvestable_profit_wei": int(self.state.reinvestable_profit_wei),
            "reinvested_profit_wei": int(self.state.reinvested_profit_wei),
            "cumulative_owned_capital_delta_wei": int(self.state.cumulative_owned_capital_delta_wei),
            "last_flashloan_principal_wei": int(self.state.last_flashloan_principal_wei),
            "last_flashloan_fee_wei": int(self.state.last_flashloan_fee_wei),
            "last_amount_in_wei": int(self.state.last_amount_in_wei),
            "success_streak": int(self.state.success_streak),
            "fail_streak": int(self.state.fail_streak),
            "updated_ts_ms": int(self.state.updated_ts_ms or 0),
            "profit_updated_ts_ms": int(self.state.profit_updated_ts_ms or 0),
            "sizing_updated_ts_ms": int(self.state.sizing_updated_ts_ms or 0),
            "recent_results": [int(v) for v in list(self.state.recent_results)],
            "recent_returns": [float(v) for v in list(self.state.recent_returns)],
        }

    def _load_state(self) -> BankrollState:
        if not self._state_path:
            return self._default_state()
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except _SAFE_BANKROLL_STATE_IO_EXCEPTIONS:
            payload = self._load_state_from_history()
            if not payload:
                return self._default_state()
        now_ms = self._now_ms()
        window = max(1, int(getattr(self.cfg, "kelly_window", 50) or 50))
        try:
            recent_results = deque(
                [int(v) for v in list(payload.get("recent_results") or [])],
                maxlen=window,
            )
        except _SAFE_BANKROLL_STATE_IO_EXCEPTIONS:
            recent_results = deque(maxlen=window)
        try:
            recent_returns = deque(
                [float(v) for v in list(payload.get("recent_returns") or [])],
                maxlen=window,
            )
        except _SAFE_BANKROLL_STATE_IO_EXCEPTIONS:
            recent_returns = deque(maxlen=window)
        legacy_profit = int(payload.get("realized_profit_wei") or 0)
        signed_pnl = int(payload.get("realized_net_pnl_wei") or legacy_profit)
        reinvestable = int(payload.get("reinvestable_profit_wei") or max(0, signed_pnl))
        return BankrollState(
            realized_profit_wei=signed_pnl,
            realized_net_pnl_wei=signed_pnl,
            bankroll_loss_wei=int(payload.get("bankroll_loss_wei") or 0),
            reinvestable_profit_wei=max(0, reinvestable),
            reinvested_profit_wei=int(payload.get("reinvested_profit_wei") or 0),
            cumulative_owned_capital_delta_wei=int(
                payload.get("cumulative_owned_capital_delta_wei") or signed_pnl
            ),
            last_flashloan_principal_wei=int(payload.get("last_flashloan_principal_wei") or 0),
            last_flashloan_fee_wei=int(payload.get("last_flashloan_fee_wei") or 0),
            last_amount_in_wei=int(payload.get("last_amount_in_wei") or 0),
            success_streak=int(payload.get("success_streak") or 0),
            fail_streak=int(payload.get("fail_streak") or 0),
            updated_ts_ms=max(0, int(payload.get("updated_ts_ms") or 0)) or now_ms,
            profit_updated_ts_ms=max(0, int(payload.get("profit_updated_ts_ms") or 0)) or now_ms,
            sizing_updated_ts_ms=max(0, int(payload.get("sizing_updated_ts_ms") or 0)) or now_ms,
            recent_results=recent_results,
            recent_returns=recent_returns,
        )

    def _load_state_from_history(self) -> dict[str, Any]:
        repo = self._history_repo
        if repo is None or not hasattr(repo, "latest_event"):
            return {}
        try:
            event = repo.latest_event()
        except _SAFE_BANKROLL_STATE_IO_EXCEPTIONS:
            return {}
        state = dict(event.get("state") or {}) if isinstance(event, dict) else {}
        return dict(state or {}) if isinstance(state, dict) else {}

    def _save_state(self) -> None:
        if not self._state_path:
            return
        try:
            state_dir = os.path.dirname(self._state_path)
            if state_dir:
                os.makedirs(state_dir, exist_ok=True)
            tmp_path = f"{self._state_path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._state_payload(), f, sort_keys=True)
            os.replace(tmp_path, self._state_path)
        except _SAFE_BANKROLL_STATE_IO_EXCEPTIONS:
            return

    def _record_history(self, *, event_type: str, payload: dict[str, Any] | None = None) -> None:
        state_payload = self._state_payload()
        event_payload = dict(payload or {})
        ts_ms = int(self.state.updated_ts_ms or 0)
        if self._history_repo is not None:
            try:
                self._history_repo.append_event(
                    ts_ms=ts_ms,
                    event_type=str(event_type or "unknown"),
                    state=state_payload,
                    payload=event_payload,
                )
            except _SAFE_BANKROLL_STATE_IO_EXCEPTIONS:
                pass
        if self._capital_event_repo is None:
            return
        try:
            self._capital_event_repo.append_event(
                ts_ms=ts_ms,
                domain="bankroll",
                event_type=str(event_type or "unknown"),
                source="bankroll_manager",
                entity_id="bankroll_state",
                payload={"state": state_payload, "payload": event_payload},
            )
        except _SAFE_BANKROLL_STATE_IO_EXCEPTIONS:
            return

    def _ensure_history_bootstrap(self) -> None:
        if self._history_repo is None:
            return
        try:
            latest = self._history_repo.latest_event()
        except _SAFE_BANKROLL_STATE_IO_EXCEPTIONS:
            latest = {}
        latest_state = dict(latest.get("state") or {}) if isinstance(latest, dict) else {}
        state_payload = self._state_payload()
        keys = (
            "realized_profit_wei",
            "realized_net_pnl_wei",
            "bankroll_loss_wei",
            "reinvestable_profit_wei",
            "reinvested_profit_wei",
            "cumulative_owned_capital_delta_wei",
            "updated_ts_ms",
            "profit_updated_ts_ms",
            "sizing_updated_ts_ms",
        )
        if latest_state and all(latest_state.get(key) == state_payload.get(key) for key in keys):
            return
        self._record_history(event_type="bootstrap")

    def _touch(self, *, profit: bool = False, sizing: bool = False) -> None:
        now_ms = self._now_ms()
        self.state.updated_ts_ms = int(now_ms)
        if profit:
            self.state.profit_updated_ts_ms = int(now_ms)
        if sizing:
            self.state.sizing_updated_ts_ms = int(now_ms)

    def project_trade_state(
        self,
        *,
        success: bool | None = None,
        realized_profit_after_gas_wei: int = 0,
        amount_in_wei: int | None = None,
        signed_net_pnl_wei: int | None = None,
        flashloan_principal_wei: int = 0,
        flashloan_fee_wei: int = 0,
    ) -> dict[str, Any]:
        """Project bankroll from a settled economic result.

        New callers should provide ``signed_net_pnl_wei`` from the canonical
        settled-outcome authority. The success flag is retained only for
        backwards compatibility and is never allowed to erase a signed loss.
        """
        payload = self._state_payload()
        amt_in = (
            int(amount_in_wei)
            if amount_in_wei is not None
            else int(payload.get("last_amount_in_wei") or 0)
        )
        amt_in = max(1, amt_in)
        payload["last_amount_in_wei"] = int(amt_in)

        if signed_net_pnl_wei is None:
            # Legacy compatibility: successful legacy calls remain positive;
            # failed legacy calls remain unknown rather than fabricating a loss.
            signed_pnl = int(realized_profit_after_gas_wei) if bool(success) else 0
        else:
            signed_pnl = int(signed_net_pnl_wei)

        previous_signed = int(payload.get("realized_net_pnl_wei") or 0)
        previous_reinvestable = max(0, int(payload.get("reinvestable_profit_wei") or 0))
        payload["realized_net_pnl_wei"] = previous_signed + signed_pnl
        # Keep the legacy field aligned with the canonical signed quantity.
        payload["realized_profit_wei"] = payload["realized_net_pnl_wei"]
        payload["bankroll_loss_wei"] = int(payload.get("bankroll_loss_wei") or 0) + max(
            0, -signed_pnl
        )
        payload["cumulative_owned_capital_delta_wei"] = int(
            payload.get("cumulative_owned_capital_delta_wei") or 0
        ) + signed_pnl
        payload["reinvestable_profit_wei"] = previous_reinvestable + max(0, signed_pnl)
        payload["last_flashloan_principal_wei"] = max(0, int(flashloan_principal_wei))
        payload["last_flashloan_fee_wei"] = max(0, int(flashloan_fee_wei))

        if signed_net_pnl_wei is not None:
            profitable = signed_pnl > 0
            if profitable:
                payload["success_streak"] = int(payload.get("success_streak") or 0) + 1
                payload["fail_streak"] = 0
            elif signed_pnl < 0:
                payload["fail_streak"] = int(payload.get("fail_streak") or 0) + 1
                payload["success_streak"] = 0
            else:
                payload["success_streak"] = 0
        elif bool(success):
            payload["success_streak"] = int(payload.get("success_streak") or 0) + 1
            payload["fail_streak"] = 0
        else:
            payload["fail_streak"] = int(payload.get("fail_streak") or 0) + 1
            payload["success_streak"] = 0

        now_ms = self._now_ms()
        payload["updated_ts_ms"] = int(now_ms)
        payload["sizing_updated_ts_ms"] = int(now_ms)
        if signed_net_pnl_wei != 0 or bool(success):
            payload["profit_updated_ts_ms"] = int(now_ms)
        else:
            payload["profit_updated_ts_ms"] = int(payload.get("profit_updated_ts_ms") or now_ms)

        results = [int(v) for v in list(self.state.recent_results)]
        returns = [float(v) for v in list(self.state.recent_returns)]
        if signed_pnl > 0:
            results.append(1)
        elif signed_pnl < 0:
            results.append(0)
        else:
            results.append(1 if bool(success) else 0)
        returns.append(float(signed_pnl) / float(amt_in))
        window = max(1, int(getattr(self.cfg, "kelly_window", 50) or 50))
        payload["recent_results"] = results[-window:]
        payload["recent_returns"] = returns[-window:]
        return payload

    def apply_state_payload(self, payload: dict[str, Any]) -> None:
        state_payload = dict(payload or {})
        window = max(1, int(getattr(self.cfg, "kelly_window", 50) or 50))
        signed_pnl = int(
            state_payload.get("realized_net_pnl_wei")
            or state_payload.get("realized_profit_wei")
            or 0
        )
        self.state = BankrollState(
            realized_profit_wei=signed_pnl,
            realized_net_pnl_wei=signed_pnl,
            bankroll_loss_wei=max(0, int(state_payload.get("bankroll_loss_wei") or 0)),
            reinvestable_profit_wei=max(0, int(state_payload.get("reinvestable_profit_wei") or 0)),
            reinvested_profit_wei=max(0, int(state_payload.get("reinvested_profit_wei") or 0)),
            cumulative_owned_capital_delta_wei=int(
                state_payload.get("cumulative_owned_capital_delta_wei") or signed_pnl
            ),
            last_flashloan_principal_wei=max(
                0, int(state_payload.get("last_flashloan_principal_wei") or 0)
            ),
            last_flashloan_fee_wei=max(0, int(state_payload.get("last_flashloan_fee_wei") or 0)),
            last_amount_in_wei=int(state_payload.get("last_amount_in_wei") or 0),
            success_streak=int(state_payload.get("success_streak") or 0),
            fail_streak=int(state_payload.get("fail_streak") or 0),
            updated_ts_ms=int(state_payload.get("updated_ts_ms") or self._now_ms()),
            profit_updated_ts_ms=int(state_payload.get("profit_updated_ts_ms") or self._now_ms()),
            sizing_updated_ts_ms=int(state_payload.get("sizing_updated_ts_ms") or self._now_ms()),
            recent_results=deque(
                [int(v) for v in list(state_payload.get("recent_results") or [])], maxlen=window
            ),
            recent_returns=deque(
                [float(v) for v in list(state_payload.get("recent_returns") or [])], maxlen=window
            ),
        )
        self._save_state()

    def _apply_configured_window(self) -> None:
        w = int(getattr(self.cfg, "kelly_window", 50) or 50)
        self.state.recent_results = deque(list(self.state.recent_results), maxlen=max(1, w))
        self.state.recent_returns = deque(list(self.state.recent_returns), maxlen=max(1, w))

    def apply_overrides(
        self, *, kelly_enabled: bool | None = None, auto_reinvest_enabled: bool | None = None
    ) -> None:
        try:
            if kelly_enabled is not None:
                self.cfg.kelly_enabled = bool(kelly_enabled)
            if auto_reinvest_enabled is not None:
                self.cfg.auto_reinvest_enabled = bool(auto_reinvest_enabled)
            self._touch()
            self._save_state()
            self._record_history(
                event_type="override",
                payload={
                    "kelly_enabled": (None if kelly_enabled is None else bool(kelly_enabled)),
                    "auto_reinvest_enabled": (
                        None if auto_reinvest_enabled is None else bool(auto_reinvest_enabled)
                    ),
                },
            )
        except _SAFE_BANKROLL_OVERRIDE_EXCEPTIONS:
            pass

    def record_trade(
        self,
        *,
        success: bool,
        realized_profit_after_gas_wei: int,
        amount_in_wei: int | None = None,
        signed_net_pnl_wei: int | None = None,
        flashloan_principal_wei: int = 0,
        flashloan_fee_wei: int = 0,
    ) -> None:
        state_payload = self.project_trade_state(
            success=bool(success),
            realized_profit_after_gas_wei=int(realized_profit_after_gas_wei),
            amount_in_wei=amount_in_wei,
            signed_net_pnl_wei=signed_net_pnl_wei,
            flashloan_principal_wei=flashloan_principal_wei,
            flashloan_fee_wei=flashloan_fee_wei,
        )
        self.apply_state_payload(state_payload)
        self._record_history(
            event_type="trade_recorded",
            payload={
                "success": bool(success),
                "signed_net_pnl_wei": int(
                    signed_net_pnl_wei
                    if signed_net_pnl_wei is not None
                    else realized_profit_after_gas_wei
                ),
                "realized_profit_after_gas_wei": int(realized_profit_after_gas_wei),
                "flashloan_principal_wei": int(flashloan_principal_wei),
                "flashloan_fee_wei": int(flashloan_fee_wei),
                "amount_in_wei": int(state_payload.get("last_amount_in_wei") or 0),
            },
        )

    def record_reinvestment(self, amount_wei: int) -> int:
        """Consume only the current reinvestable-profit pool."""
        amount = max(0, int(amount_wei))
        consumed = min(amount, max(0, int(self.state.reinvestable_profit_wei)))
        if consumed <= 0:
            return 0
        self.state.reinvestable_profit_wei -= consumed
        self.state.reinvested_profit_wei += consumed
        self._touch(sizing=True)
        self._save_state()
        self._record_history(
            event_type="profit_reinvested",
            payload={"amount_wei": int(consumed)},
        )
        return consumed

    def success_rate_pct(self) -> float:
        if not self.state.recent_results:
            return 0.0
        return 100.0 * (sum(self.state.recent_results) / len(self.state.recent_results))

    def next_amount_in(self) -> int:
        base = max(0, int(self.cfg.base_borrow_amount_wei))
        if base <= 0:
            return 0
        cap = max(0, int(self.cfg.max_borrow_amount_wei))
        if not self.cfg.auto_reinvest_enabled or self.cfg.reinvest_rate_pct <= 0:
            amt = int(base)
        else:
            reinvest = (
                int(self.state.reinvestable_profit_wei) * int(self.cfg.reinvest_rate_pct)
            ) // 100
            amt = int(base + reinvest)

        if bool(self.cfg.kelly_enabled) and len(self.state.recent_returns) >= int(
            getattr(self.cfg, "kelly_min_history", 20) or 20
        ):
            kf = self._kelly_fraction()
            scale = max(0.25, min(3.0, 0.5 + 2.0 * float(kf)))
            amt = int(max(1, int(float(amt) * float(scale))))
        if cap > 0:
            amt = min(amt, cap)
        if self.state.fail_streak >= 2:
            amt = max(base, amt // 2)
        if cap > 0:
            amt = min(amt, cap)
        self.state.last_amount_in_wei = amt
        self._touch(sizing=True)
        self._save_state()
        self._record_history(
            event_type="sizing_decision",
            payload={
                "recommended_amount_in_wei": int(amt),
                "reinvestable_profit_wei": int(self.state.reinvestable_profit_wei),
                "flashloan_principal_excluded": True,
            },
        )
        return amt

    def _kelly_fraction(self) -> float:
        rets = list(self.state.recent_returns)
        if not rets:
            return float(self.cfg.kelly_min_fraction)

        mu = sum(float(r) for r in rets) / float(len(rets))
        var = sum((float(r) - mu) ** 2 for r in rets) / float(max(1, len(rets) - 1))
        p = float(sum(1 for r in rets if float(r) > 0.0)) / float(len(rets))
        vd = float(self.cfg.volatility_downscale)
        if var <= 1e-12:
            f = float(p) * 0.10
        else:
            f = (mu / var) * (0.5 + 0.5 * p)
        f = max(0.0, f)
        f = f * (1.0 - max(0.0, min(0.80, vd)))
        return float(
            max(float(self.cfg.kelly_min_fraction), min(float(self.cfg.kelly_cap_fraction), f))
        )
