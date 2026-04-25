from __future__ import annotations

from typing import Any, Dict

from ..ids import make_decision_id, make_replay_event_id, stable_json_hash


def verify_replay_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    data = dict(bundle or {})
    stored_hash = str(data.get("event_hash") or "")
    computed_hash = stable_json_hash({k: v for k, v in data.items() if k != "event_hash"})
    decision_id = make_decision_id(
        chain_id=int(data.get("chain_id") or 0),
        block_number=int(data.get("block_number") or 0),
        opportunity_id=str(data.get("opportunity_id") or ""),
        route_id=str(data.get("route_id") or ""),
        mode=str(
            ((data.get("execution") or {}) if isinstance(data.get("execution"), dict) else {}).get(
                "mode"
            )
            or ""
        ),
        rl_state=str(
            (
                (
                    (data.get("execution") or {}) if isinstance(data.get("execution"), dict) else {}
                ).get("rl_state")
                or ""
            )
        ),
        rl_action=int(
            (
                (
                    (data.get("execution") or {}) if isinstance(data.get("execution"), dict) else {}
                ).get("rl_action")
                or -1
            )
        ),
    )
    event_id = make_replay_event_id(
        chain_id=int(data.get("chain_id") or 0),
        block_number=int(data.get("block_number") or 0),
        opportunity_id=str(data.get("opportunity_id") or ""),
        route_id=str(data.get("route_id") or ""),
        decision_id=str(decision_id),
    )
    ok = (
        stored_hash == computed_hash
        and str(data.get("decision_id") or "") == decision_id
        and str(data.get("event_id") or "") == event_id
    )
    return {
        "ok": bool(ok),
        "event_id": str(data.get("event_id") or ""),
        "decision_id": str(data.get("decision_id") or ""),
        "computed_event_id": str(event_id),
        "computed_decision_id": str(decision_id),
        "stored_hash": stored_hash,
        "computed_hash": computed_hash,
    }
