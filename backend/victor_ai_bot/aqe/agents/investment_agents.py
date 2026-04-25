from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Tuple, Optional

from ..core.actions import ActionSpec, actions_from_rl, dist_for_action, normalize_dist
from .base import AgentOutput
from .adaptation import OnlineLinearCalibrator


_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError, OverflowError)
_SAFE_MAPPING_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError)
_SAFE_CALIBRATOR_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError)


def _status(ok: bool, code: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": bool(ok), "code": str(code)}
    payload.update(extra)
    return payload


def _merge_status(base: Dict[str, Any], key: str, status: Dict[str, Any]) -> None:
    base[key] = dict(status)


def _runtime_snapshot(parts: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {k: dict(v) for k, v in parts.items()}
    payload["degraded"] = any(
        isinstance(v, dict) and not bool(v.get("ok", False)) for v in payload.values()
    )
    return payload


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _coerce_float(value: Any, default: float) -> Tuple[float, bool]:
    try:
        return float(value if value is not None else default), True
    except _SAFE_FLOAT_EXCEPTIONS:
        return float(default), False


def _coerce_feature_map(
    features: Mapping[str, Any] | Dict[str, Any] | None
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    out: Dict[str, float] = {}
    invalid: List[str] = []
    for k, v in dict(features or {}).items():
        fv, ok = _coerce_float(v, 0.0)
        out[str(k)] = float(fv)
        if not ok:
            invalid.append(str(k))
    status = _status(
        not bool(invalid), "features_ok" if not invalid else "features_coerced", invalid=invalid
    )
    return out, status


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-float(x)))
    except _SAFE_FLOAT_EXCEPTIONS:
        return 0.5


def _uniform(actions: List[ActionSpec]) -> Dict[str, float]:
    if not actions:
        return {}
    p = 1.0 / len(actions)
    return {a.key(): p for a in actions}


def _pick_closest_action(
    actions: List[ActionSpec], *, gas: str, size: float, borrow: float
) -> ActionSpec:
    best = actions[0]
    best_d = 1e9
    for a in actions:
        d = 0.0
        d += 0.0 if a.gas_mode == gas else 1.0
        d += abs(float(a.size_mult) - float(size))
        d += abs(float(a.borrow_mult) - float(borrow))
        if d < best_d:
            best_d = d
            best = a
    return best


@dataclass
class FeatureView:
    """Reads the enriched CAQ-KDS state with safe defaults."""

    state: Dict[str, Any]
    S: Dict[str, Any] = field(init=False)
    C: Dict[str, Any] = field(init=False)
    H: Dict[str, Any] = field(init=False)
    _runtime: Dict[str, Dict[str, Any]] = field(init=False)

    def __post_init__(self) -> None:
        self.state = dict(self.state or {})
        raw_s = self.state.get("S_global")
        raw_c = self.state.get("C_t")
        raw_h = self.state.get("Historical_Context")
        self.S = dict(raw_s) if isinstance(raw_s, dict) else {}
        self.C = dict(raw_c) if isinstance(raw_c, dict) else {}
        self.H = dict(raw_h) if isinstance(raw_h, dict) else {}
        self._runtime = {
            "features": _status(True, "features_idle"),
            "historical": _status(True, "historical_idle"),
            "context": _status(True, "context_idle"),
            "state": _status(True, "state_idle"),
            "strings": _status(True, "strings_idle"),
            "embedding": _status(True, "embedding_idle"),
        }

    def f(self, key: str, default: float = 0.0) -> float:
        feats = self.S.get("features")
        if isinstance(feats, dict) and key in feats:
            value, ok = _coerce_float(feats.get(key, default), default)
            if ok:
                _merge_status(self._runtime, "features", _status(True, "features_ok", source=key))
                return value
            _merge_status(self._runtime, "features", _status(False, "features_invalid", source=key))
        if key in self.H:
            value, ok = _coerce_float(self.H.get(key, default), default)
            if ok:
                _merge_status(
                    self._runtime, "historical", _status(True, "historical_ok", source=key)
                )
                return value
            _merge_status(
                self._runtime, "historical", _status(False, "historical_invalid", source=key)
            )
        if key in self.C:
            value, ok = _coerce_float(self.C.get(key, default), default)
            if ok:
                _merge_status(self._runtime, "context", _status(True, "context_ok", source=key))
                return value
            _merge_status(self._runtime, "context", _status(False, "context_invalid", source=key))
        value, ok = _coerce_float(self.state.get(key, default), default)
        if ok:
            _merge_status(self._runtime, "state", _status(True, "state_ok", source=key))
            return value
        _merge_status(self._runtime, "state", _status(False, "state_invalid", source=key))
        return float(default)

    def s(self, key: str, default: str = "") -> str:
        value = default
        if key == "regime" and "regime" in self.S:
            value = self.S.get("regime", default)
        else:
            value = self.state.get(key, default)
        try:
            out = str(value if value is not None else default)
            _merge_status(self._runtime, "strings", _status(True, "strings_ok", source=key))
            return out
        except _SAFE_MAPPING_EXCEPTIONS:
            _merge_status(self._runtime, "strings", _status(False, "strings_invalid", source=key))
            return str(default)

    def embedding(self) -> List[float]:
        e = self.S.get("embedding") or []
        if not isinstance(e, list):
            _merge_status(self._runtime, "embedding", _status(False, "embedding_invalid_type"))
            return []
        out: List[float] = []
        invalid = 0
        for x in e[:64]:
            val, ok = _coerce_float(x, 0.0)
            if ok:
                out.append(float(val))
            else:
                invalid += 1
        _merge_status(
            self._runtime,
            "embedding",
            _status(
                invalid == 0,
                "embedding_ok" if invalid == 0 else "embedding_partial",
                invalid=invalid,
                length=len(out),
            ),
        )
        return out

    def runtime_state(self) -> Dict[str, Any]:
        return _runtime_snapshot(self._runtime)


@dataclass
class DomainAgentBase:
    name: str
    data_dir: str = ""
    # style affects exploration alpha defaults
    style: str = "balanced"  # conservative|balanced|aggressive
    # Learning is safe to keep on by default (it only affects scoring), but can
    # be explicitly disabled via env VICTOR_AGENT_LEARN=0.
    learn: bool = True

    def __post_init__(self) -> None:
        # Deterministic learning enablement:
        # - if env is set, it is authoritative
        # - else keep default self.learn
        env = os.environ.get("VICTOR_AGENT_LEARN")
        if env is not None:
            self.learn = bool(str(env) == "1")
        self.cal = OnlineLinearCalibrator(
            name=self.name, data_dir=self.data_dir or "backend/data", enabled=self.learn
        )
        self._last_update_status = _status(True, "adaptation_idle")

    # ---- domain specialization override points ----
    def compute(self, fv: FeatureView) -> Tuple[float, float, Dict[str, Any], Dict[str, float]]:
        """Return (signal, confidence, reasoning, features_used)."""
        return 0.0, 0.3, {"note": "base"}, {}

    def _alpha_default(self) -> float:
        if self.style == "conservative":
            return 0.04
        if self.style == "aggressive":
            return 0.10
        return 0.07

    def _policy_from_signal(
        self, fv: FeatureView, *, signal: float, confidence: float
    ) -> Tuple[str, float, float]:
        """Map signal to (gas, size_mult, borrow_mult)."""
        mr = fv.f("local.margin_ratio", fv.f("margin_ratio", 0.0))
        gr = abs(fv.f("local.gas_ratio", fv.f("gas_ratio", 0.0)))
        p = fv.f("local.p_success", fv.f("p_success", 0.75))
        legs = int(fv.f("local.legs", fv.f("legs", 2)))

        # default conservative posture
        gas = "standard"
        size = 0.75
        borrow = 1.0

        # Treasury overlay (deterministic): may raise or cap borrow sizing.
        trea_lvl = str(
            fv.s(
                "treasury.effective_aggressiveness_level",
                fv.s("treasury.aggressiveness_level", "LOW"),
            )
            or "LOW"
        ).upper()
        trea_cap = float(
            fv.f(
                "treasury.effective_borrow_mult_target_cap",
                fv.f("treasury.borrow_mult_target_cap", 1.5),
            )
            or 1.5
        )
        urgency = float(fv.f("treasury.urgency_factor", 0.0) or 0.0)

        # signal indicates risk-on (+) vs risk-off (-)
        if signal <= -0.55:
            size = 0.5
            borrow = 0.75
            gas = "standard"
        elif signal <= -0.10:
            size = 0.75
            borrow = 1.0
            gas = "standard"
        elif signal <= 0.35:
            size = 1.0
            borrow = 1.0
            gas = "standard"
        else:
            # positive conviction, but still gated by safety
            size = 1.0
            borrow = 1.5 if (confidence > 0.65 and p > 0.85 and mr > 0.0010) else 1.0
            # Dynamic borrow scaling for large/urgent trades (still capped later by treasury & safety).
            if (
                trea_lvl in {"HIGH", "MAXIMUM"}
                and confidence > 0.72
                and p > 0.90
                and mr > 0.0018
                and legs <= 2
            ):
                # urgency provides a deterministic incremental bump.
                bump = 0.25 if trea_lvl == "HIGH" else 0.50
                bump *= max(1.0, min(1.30, 1.0 + max(0.0, urgency) * 0.10))
                borrow = max(borrow, 1.5 + bump)
            # gas mode upgrades only when margins allow and gas_ratio isn't high
            if mr > 0.0018 and gr < 0.0007:
                gas = "fast"
            if mr > 0.0028 and gr < 0.00045 and p > 0.90:
                gas = "instant"

        # penalize complexity
        if legs >= 3:
            size = min(size, 0.75)
            borrow = min(borrow, 1.5)

        # cap by treasury target and global rational limits
        borrow = min(borrow, max(1.0, float(trea_cap)))
        borrow = float(_clip(borrow, 0.5, 3.0))

        # if success probability low, pull back
        if p < 0.70:
            size = min(size, 0.5)
            gas = "standard"
            borrow = min(borrow, 1.0)

        return gas, float(size), float(borrow)

    def act(self, *, state: Dict[str, Any]) -> AgentOutput:
        actions = actions_from_rl()
        fv = FeatureView(state)

        sig, conf, reasoning, feats_used = self.compute(fv)
        runtime = {
            "feature_view": fv.runtime_state(),
            "calibration": _status(True, "calibration_idle"),
            "adaptation": dict(self._last_update_status),
        }
        coerced_feats, feat_status = _coerce_feature_map(feats_used)
        runtime["features_used"] = feat_status
        # apply optional learned calibrator adjustment (bounded)
        try:
            delta = float(self.cal.apply(coerced_feats))
            sig = float(_clip(float(sig) + delta, -1.0, 1.0))
            runtime["calibration"] = dict(self.cal.state())
        except _SAFE_CALIBRATOR_EXCEPTIONS:
            sig = float(_clip(sig, -1.0, 1.0))
            runtime["calibration"] = _status(False, "calibration_apply_failed")

        conf = float(_clip(conf, 0.05, 1.0))

        gas, size, borrow = self._policy_from_signal(fv, signal=float(sig), confidence=float(conf))
        chosen = _pick_closest_action(actions, gas=gas, size=size, borrow=borrow)
        pi_team = dist_for_action(chosen, actions, p=0.92 if self.style != "aggressive" else 0.90)

        # π_self exploration: bounded high-entropy mix; slightly biased away from chosen
        pi_self = _uniform(actions)
        if actions:
            for a in actions:
                w = 1.0
                if a.gas_mode != chosen.gas_mode:
                    w *= 1.15
                if float(a.size_mult) != float(chosen.size_mult):
                    w *= 1.10
                if float(a.borrow_mult) != float(chosen.borrow_mult):
                    w *= 1.05
                pi_self[a.key()] = float(pi_self.get(a.key(), 0.0)) * w
            pi_self = normalize_dist(pi_self)

        alpha = float(_clip(self._alpha_default(), 0.0, 1.0))

        # Q proxy: base EV scaled by action notional, damped by risk
        ev = float(fv.f("local.ev", fv.f("ev_wei", 0.0)) or 0.0)
        risk = float(fv.f("risk_level", 0.0) or 0.0)
        q: Dict[str, float] = {}
        for a in actions:
            notional = max(0.10, float(a.size_mult) * float(a.borrow_mult))
            gas_pen = 1.0
            if a.gas_mode == "fast":
                gas_pen = 1.15
            elif a.gas_mode == "instant":
                gas_pen = 1.30
            q[a.key()] = ev * notional / gas_pen * (1.0 - 0.4 * _clip(risk, 0.0, 1.0))

        info = {
            "name": self.name,
            "style": self.style,
            "chosen": chosen.key(),
            "regime": fv.s("regime", "unknown"),
            "runtime": runtime,
        }
        info.update({"signal": float(sig), "confidence": float(conf)})

        reasoning_payload = dict(reasoning or {})
        reasoning_payload.setdefault("runtime", runtime)

        return AgentOutput(
            pi_team=pi_team,
            pi_self=pi_self,
            alpha=alpha,
            q_values=q,
            confidence=float(conf),
            info=info,
            signal=float(_clip(sig, -1.0, 1.0)),
            features_used=coerced_feats,
            reasoning=reasoning_payload,
        )

    def update(self, *, reward: float, features_used: Dict[str, float]) -> None:
        """Optional adaptation hook."""
        reward_value, reward_ok = _coerce_float(reward, 0.0)
        feature_map, feat_status = _coerce_feature_map(features_used)
        if not reward_ok:
            self._last_update_status = _status(False, "adaptation_reward_invalid")
            return
        try:
            self.cal.update(reward=float(reward_value), features=feature_map)
            self._last_update_status = _status(
                bool(feat_status.get("ok", False)),
                (
                    "adaptation_updated"
                    if bool(feat_status.get("ok", False))
                    else "adaptation_features_coerced"
                ),
                invalid=list(feat_status.get("invalid") or []),
                calibration=self.cal.state(),
            )
        except _SAFE_CALIBRATOR_EXCEPTIONS:
            self._last_update_status = _status(False, "adaptation_update_failed")


# -------------------------
# Specialized domain agents
# -------------------------


class BenGrahamAgent(DomainAgentBase):
    """Deep discount / margin of safety: prefer thick spreads with strong buffers."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Ben Graham Agent", data_dir=data_dir, style="conservative")

    def compute(self, fv: FeatureView):
        mr = fv.f("local.margin_ratio", 0.0)
        gr = abs(fv.f("local.gas_ratio", 0.0))
        legs = fv.f("local.legs", 2.0)
        liq = fv.f("cex.depth_usd", 0.0)
        vol = fv.f("mev.sandwich_risk", 0.0) + 0.5 * abs(fv.f("cex.funding_change_bps", 0.0)) / 10.0
        # margin of safety proxy
        mos = mr - (0.00015 * max(0.0, legs - 2.0)) - 0.50 * gr - 0.00010 * _clip(vol, 0.0, 1.0)
        # normalized signal
        signal = _clip(mos / 0.0012, -1.0, 1.0)
        conf = _clip(0.20 + 0.70 * _sigmoid(1800.0 * mos), 0.05, 1.0)
        feats = {"mr": mr, "gr": gr, "legs": legs, "liq": liq, "mos": mos, "vol": vol}
        reasoning = {"margin_of_safety": mos, "note": "prefers thick spreads and buffers"}
        return float(signal), float(conf), reasoning, feats


class WarrenBuffettAgent(DomainAgentBase):
    """Moat + ROIC stability proxy via reliability/consistency."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Warren Buffett Agent", data_dir=data_dir, style="conservative")

    def compute(self, fv: FeatureView):
        rel = fv.f("rel.reliability", 0.0)
        p = fv.f("local.p_success", 0.75)
        fail_rate = fv.f("dex.route_fail_rate", 0.0)
        mr = fv.f("local.margin_ratio", 0.0)
        stability = _clip(
            0.55 * rel + 0.35 * p + 0.10 * (1.0 - _clip(fail_rate, 0.0, 1.0)), 0.0, 1.0
        )
        signal = _clip((stability - 0.50) * 2.0, -1.0, 1.0)
        # Buffett prefers only positive sizing when spreads exist
        if mr < 0.0004:
            signal = min(signal, 0.0)
        conf = _clip(0.25 + 0.70 * stability, 0.05, 1.0)
        feats = {
            "reliability": rel,
            "p": p,
            "fail_rate": fail_rate,
            "stability": stability,
            "mr": mr,
        }
        reasoning = {"stability": stability, "note": "prefers consistent, durable routes"}
        return float(signal), float(conf), reasoning, feats


class CharlieMungerAgent(DomainAgentBase):
    """Quality + durability: penalize complexity and low-liquidity conditions."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Charlie Munger Agent", data_dir=data_dir, style="balanced")

    def compute(self, fv: FeatureView):
        mr = fv.f("local.margin_ratio", 0.0)
        legs = fv.f("local.legs", 2.0)
        depth = fv.f("cex.depth_usd", 0.0)
        spread = fv.f("cex.spread_bps", 0.0)
        # quality proxy: good depth, tight spread, fewer legs, decent margin
        q = _clip(
            0.40 * _clip(depth, 0.0, 3.0)
            + 0.25 * _clip(1.0 - spread / 50.0, 0.0, 1.0)
            + 0.20 * _clip(mr / 0.0015, 0.0, 1.0)
            + 0.15 * _clip(1.0 - (legs - 2.0) / 2.0, 0.0, 1.0),
            0.0,
            1.0,
        )
        signal = _clip((q - 0.5) * 2.0, -1.0, 1.0)
        conf = _clip(0.20 + 0.75 * q, 0.05, 1.0)
        feats = {"mr": mr, "legs": legs, "depth": depth, "spread_bps": spread, "quality": q}
        reasoning = {"quality": q, "note": "prefers durable quality execution conditions"}
        return float(signal), float(conf), reasoning, feats


class CathieWoodAgent(DomainAgentBase):
    """Disruptive innovation score proxy: thrives in opportunity-rich regimes."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Cathie Wood Agent", data_dir=data_dir, style="aggressive")

    def compute(self, fv: FeatureView):
        regime = fv.s("regime", "normal")
        opps = fv.f("dex.opps_per_block", 0.0)
        mr = fv.f("local.margin_ratio", 0.0)
        vol = fv.f("mev.sandwich_risk", 0.0)
        innovation = _clip(
            0.50 * _clip(opps / 6.0, 0.0, 1.0)
            + 0.30 * _clip(mr / 0.0020, 0.0, 1.0)
            + 0.20 * _clip(vol, 0.0, 1.0),
            0.0,
            1.0,
        )
        signal = _clip((innovation - 0.45) * 2.2, -1.0, 1.0)
        conf = _clip(0.15 + 0.70 * innovation, 0.05, 1.0)
        feats = {"opps": opps, "mr": mr, "vol": vol, "innovation": innovation}
        reasoning = {
            "innovation": innovation,
            "regime": regime,
            "note": "prefers opportunity-rich regimes",
        }
        return float(signal), float(conf), reasoning, feats


class PhilFisherAgent(DomainAgentBase):
    """Scuttlebutt + acceleration proxy via momentum of spreads/funding."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Phil Fisher Agent", data_dir=data_dir, style="balanced")
        self._last_mr: Optional[float] = None
        self._last_funding: Optional[float] = None

    def compute(self, fv: FeatureView):
        mr = fv.f("local.margin_ratio", 0.0)
        fund = fv.f("cex.funding_bps", 0.0)
        acc_mr = 0.0
        acc_f = 0.0
        if self._last_mr is not None:
            acc_mr = float(mr - float(self._last_mr))
        if self._last_funding is not None:
            acc_f = float(fund - float(self._last_funding))
        self._last_mr = mr
        self._last_funding = fund
        accel = _clip(
            0.70 * _clip(acc_mr / 0.0008, -1.0, 1.0) + 0.30 * _clip(acc_f / 5.0, -1.0, 1.0),
            -1.0,
            1.0,
        )
        signal = _clip(0.6 * _clip(mr / 0.0015, -1.0, 1.0) + 0.4 * accel, -1.0, 1.0)
        conf = _clip(0.20 + 0.65 * _sigmoid(900.0 * mr) * (0.65 + 0.35 * abs(accel)), 0.05, 1.0)
        feats = {"mr": mr, "fund": fund, "acc_mr": acc_mr, "acc_f": acc_f, "accel": accel}
        reasoning = {"acceleration": accel, "note": "prefers accelerating regimes"}
        return float(signal), float(conf), reasoning, feats


class StanleyDruckenmillerAgent(DomainAgentBase):
    """Macro asymmetry detector: adapts to vol/gas regimes conservatively."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Stanley Druckenmiller Agent", data_dir=data_dir, style="balanced")

    def compute(self, fv: FeatureView):
        regime = fv.s("regime", "normal")
        vol_cluster = int((fv.state.get("S_global") or {}).get("vol_cluster", 0) or 0)
        gr = abs(fv.f("local.gas_ratio", 0.0))
        fund_chg = abs(fv.f("cex.funding_change_bps", 0.0))
        asym = _clip(
            0.45 * _clip(fund_chg / 10.0, 0.0, 1.0)
            + 0.35 * _clip(gr / 0.001, 0.0, 1.0)
            + 0.20 * _clip(vol_cluster / 3.0, 0.0, 1.0),
            0.0,
            1.0,
        )
        # when asymmetry high, prefer risk-off unless margin is huge
        mr = fv.f("local.margin_ratio", 0.0)
        signal = _clip(_clip(mr / 0.0022, 0.0, 1.0) - 1.2 * asym, -1.0, 1.0)
        conf = _clip(0.25 + 0.60 * (0.6 * _sigmoid(800.0 * mr) + 0.4 * (1.0 - asym)), 0.05, 1.0)
        feats = {
            "regime": float(vol_cluster),
            "asym": asym,
            "mr": mr,
            "gas": gr,
            "fund_chg": fund_chg,
        }
        reasoning = {
            "asymmetry": asym,
            "regime": regime,
            "note": "reduces exposure during macro instability",
        }
        return float(signal), float(conf), reasoning, feats


class BillAckmanAgent(DomainAgentBase):
    """Event-driven catalyst modeling proxy via mempool/liquidation anomalies."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Bill Ackman Agent", data_dir=data_dir, style="aggressive")

    def compute(self, fv: FeatureView):
        mev_flow = fv.f("mev.router_flow", 0.0)
        liq = fv.f("liq.intensity", 0.0)
        whale = fv.f("wallets.whale", 0.0)
        mr = fv.f("local.margin_ratio", 0.0)
        catalyst = _clip(
            0.45 * _clip(mev_flow, 0.0, 1.0)
            + 0.35 * _clip(liq, 0.0, 1.0)
            + 0.20 * _clip(whale, 0.0, 1.0),
            0.0,
            1.0,
        )
        signal = _clip(_clip(mr / 0.0018, -1.0, 1.0) + 0.35 * (catalyst - 0.5), -1.0, 1.0)
        conf = _clip(0.20 + 0.70 * (0.55 * _sigmoid(900.0 * mr) + 0.45 * catalyst), 0.05, 1.0)
        feats = {"mev_flow": mev_flow, "liq": liq, "whale": whale, "catalyst": catalyst, "mr": mr}
        reasoning = {"catalyst": catalyst, "note": "reacts to catalyst-like anomalies"}
        return float(signal), float(conf), reasoning, feats


# -------------------------
# Signal agents (feature-specific)
# -------------------------


class ValuationAgent(DomainAgentBase):
    """Intrinsic value delta proxy via DEX vs CEX mid-price divergence."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Valuation Agent", data_dir=data_dir, style="balanced")

    def compute(self, fv: FeatureView):
        # these are optional; default safe 0
        dex_mid = fv.f("dex.mid", 0.0)
        cex_mid = fv.f("cex.mid", 0.0)
        spread = fv.f("cex.spread_bps", 0.0)
        if cex_mid <= 0.0 or dex_mid <= 0.0:
            delta = 0.0
        else:
            delta = (dex_mid - cex_mid) / cex_mid  # + means dex expensive
        # signal wants to exploit divergence magnitude, direction encodes buy/short preference
        # For this engine, sign is used as *sizing* bias (magnitude matters)
        signal = _clip(delta / 0.0025, -1.0, 1.0)
        conf = _clip(
            0.15 + 0.70 * _sigmoid(abs(delta) * 1500.0) * _clip(1.0 - spread / 80.0, 0.0, 1.0),
            0.05,
            1.0,
        )
        feats = {"dex_mid": dex_mid, "cex_mid": cex_mid, "delta": delta, "spread_bps": spread}
        reasoning = {
            "intrinsic_delta": delta,
            "note": "uses mid-price divergence as valuation delta",
        }
        return float(signal), float(conf), reasoning, feats


class SentimentAgent(DomainAgentBase):
    """NLP market sentiment (optional feed). Default is neutral if unavailable."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Sentiment Agent", data_dir=data_dir, style="balanced")

    def compute(self, fv: FeatureView):
        s = fv.f("sent.score", 0.0)
        # sentiment directly maps to signal
        signal = _clip(s, -1.0, 1.0)
        conf = _clip(0.20 + 0.60 * abs(signal), 0.05, 1.0)
        feats = {"sent": s}
        reasoning = {"sentiment": s, "note": "neutral unless sentiment feed configured"}
        return float(signal), float(conf), reasoning, feats


class FundamentalsAgent(DomainAgentBase):
    """On-chain fundamentals proxy via wallet flow + whale intensity."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Fundamentals Agent", data_dir=data_dir, style="conservative")

    def compute(self, fv: FeatureView):
        flow = fv.f("wallets.flow", 0.0)
        whale = fv.f("wallets.whale", 0.0)
        # positive flow and whale accumulation increases confidence; negative decreases
        score = _clip(0.70 * _clip(flow, -1.0, 1.0) + 0.30 * _clip(whale, -1.0, 1.0), -1.0, 1.0)
        signal = float(score)
        conf = _clip(0.20 + 0.65 * abs(score), 0.05, 1.0)
        feats = {"flow": flow, "whale": whale, "score": score}
        reasoning = {"fundamentals": score, "note": "uses wallet flow proxies"}
        return float(signal), float(conf), reasoning, feats


class TechnicalsAgent(DomainAgentBase):
    """Trend + momentum + volatility proxy. Uses optional CEX mid/vol streams."""

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Technicals Agent", data_dir=data_dir, style="balanced")
        self._ema_fast: Optional[float] = None
        self._ema_slow: Optional[float] = None

    def compute(self, fv: FeatureView):
        mid = fv.f("cex.mid", 0.0)
        vol = fv.f("liq.intensity", 0.0) + fv.f("mev.sandwich_risk", 0.0)
        if mid > 0.0:
            if self._ema_fast is None or self._ema_slow is None:
                self._ema_fast = mid
                self._ema_slow = mid
            ema_fast_prev = float(self._ema_fast)
            ema_slow_prev = float(self._ema_slow)
            self._ema_fast = 0.20 * mid + 0.80 * ema_fast_prev
            self._ema_slow = 0.05 * mid + 0.95 * ema_slow_prev
            mom = (float(self._ema_fast) - float(self._ema_slow)) / max(1e-9, float(self._ema_slow))
        else:
            mom = 0.0
        # in arb context, momentum is used as risk-on/off indicator
        signal = _clip(mom / 0.003, -1.0, 1.0) * (1.0 - 0.5 * _clip(vol, 0.0, 1.0))
        conf = _clip(0.20 + 0.60 * abs(signal) + 0.15 * (1.0 - _clip(vol, 0.0, 1.0)), 0.05, 1.0)
        feats = {"mid": mid, "mom": mom, "vol": vol}
        reasoning = {"momentum": mom, "note": "uses EMA momentum + volatility dampening"}
        return float(signal), float(conf), reasoning, feats


class RiskManagerAgent(DomainAgentBase):
    """Risk manager: VaR/drawdown/vol exposure (full metrics in Phase 12).

    Here we produce a risk-off signal when volatility / drawdown proxies are high.
    """

    def __init__(self, *, data_dir: str = ""):
        super().__init__(name="Risk Manager", data_dir=data_dir, style="conservative")

    def compute(self, fv: FeatureView):
        # reliability module may publish these later; safe defaults
        dd = abs(fv.f("rel.drawdown", 0.0))
        sharpe = fv.f("rel.sharpe", 0.0)
        vol = fv.f("mev.sandwich_risk", 0.0) + 0.5 * abs(fv.f("cex.funding_change_bps", 0.0)) / 10.0
        risk = _clip(
            0.55 * _clip(dd, 0.0, 1.0)
            + 0.35 * _clip(vol, 0.0, 1.0)
            + 0.10 * _clip(0.5 - sharpe / 4.0, 0.0, 1.0),
            0.0,
            1.0,
        )
        # negative signal encourages downsize
        signal = _clip(-risk * 1.15, -1.0, 0.0)
        conf = _clip(0.30 + 0.60 * risk, 0.05, 1.0)
        feats = {"drawdown": dd, "sharpe": sharpe, "vol": vol, "risk": risk}
        reasoning = {"risk": risk, "note": "caps exposure when risk rises"}
        return float(signal), float(conf), reasoning, feats


def default_agent_set(*, data_dir: str = "") -> List[DomainAgentBase]:
    """Default agent set for the Investment Agent Layer.

    All agents:
      - output independent signal in [-1, +1]
      - output confidence
      - include reasoning + features_used
      - are modular and replaceable
      - support optional online adaptation (opt-in)
    """
    return [
        BenGrahamAgent(data_dir=data_dir),
        WarrenBuffettAgent(data_dir=data_dir),
        CharlieMungerAgent(data_dir=data_dir),
        CathieWoodAgent(data_dir=data_dir),
        PhilFisherAgent(data_dir=data_dir),
        StanleyDruckenmillerAgent(data_dir=data_dir),
        BillAckmanAgent(data_dir=data_dir),
        ValuationAgent(data_dir=data_dir),
        SentimentAgent(data_dir=data_dir),
        FundamentalsAgent(data_dir=data_dir),
        TechnicalsAgent(data_dir=data_dir),
        RiskManagerAgent(data_dir=data_dir),
    ]
