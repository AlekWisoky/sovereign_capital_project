from __future__ import annotations

from typing import Any, Dict

from ..risk_engine.dashboard_metrics import cio_dashboard_metrics
from .summary_read_contract import build_summary_read_contract


class CIOService:
    def summary(self, runtime: Any) -> Dict[str, Any]:
        fund = runtime.fund_state() if hasattr(runtime, "fund_state") else {}
        payload = cio_dashboard_metrics(
            capital=dict((fund or {}).get("capital") or {}),
            risk=dict((fund or {}).get("risk") or {}),
            alpha=dict((fund or {}).get("alphaPlatform") or {}),
            research=dict((fund or {}).get("researchPipeline") or {}),
            internal_prime=dict((fund or {}).get("internalPrime") or {}),
        )
        payload["summaryContract"] = build_summary_read_contract(
            family="cio",
            payload=payload,
            phase="cio_summary",
            read_model="cio_summary_projection_v1",
        )
        return payload
