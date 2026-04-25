from __future__ import annotations

import time
from typing import Any, Dict


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


INJECTION_MARKERS = [
    "ignore previous",
    "system prompt",
    "developer message",
    "reveal your",
    "exfiltrate",
    "bypass",
    "jailbreak",
]


class ThreatMonitor:
    """Threat model monitoring module.

    Outputs deterministic scores based on provided signals.
    """

    def __init__(self):
        self.last: Dict[str, Any] = {}

    def update(
        self, *, text_inputs: str = "", signals: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        s = dict(signals or {})
        txt = str(text_inputs or "").lower()

        inj = 0.0
        for m in INJECTION_MARKERS:
            if m in txt:
                inj += 0.15
        inj = float(_clip(inj, 0.0, 1.0))

        # Data spoof proxy: large deviations / stale feeds
        data_spoof = float(_clip(float(s.get("data_spoof_score", 0.0) or 0.0), 0.0, 1.0))
        cred = 1.0 if bool(s.get("credential_exposure_flag", False)) else 0.0
        replay = float(_clip(float(s.get("replay_attack_risk", 0.0) or 0.0), 0.0, 1.0))
        mev_conflict = float(_clip(float(s.get("mev_bundle_conflict_score", 0.0) or 0.0), 0.0, 1.0))
        collusion = float(_clip(float(s.get("agent_collusion_probability", 0.0) or 0.0), 0.0, 1.0))

        # Aggregate
        severity = float(
            _clip(
                0.35 * inj
                + 0.20 * data_spoof
                + 0.20 * mev_conflict
                + 0.15 * replay
                + 0.10 * collusion
                + 0.30 * cred,
                0.0,
                1.0,
            )
        )
        escalate = severity > 0.70

        out = {
            "ts": int(time.time()),
            "prompt_injection_score": float(inj),
            "data_spoof_score": float(data_spoof),
            "credential_exposure_flag": bool(cred > 0.0),
            "replay_attack_risk": float(replay),
            "mev_bundle_conflict_score": float(mev_conflict),
            "agent_collusion_probability": float(collusion),
            "severity": float(severity),
            "escalate": bool(escalate),
        }
        self.last = out
        return dict(out)

    def snapshot(self) -> Dict[str, Any]:
        return dict(self.last)
