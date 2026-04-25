from __future__ import annotations

import hashlib
import json
from typing import Any


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_json_hash(obj: Any) -> str:
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()


def _stable_id(prefix: str, **parts: Any) -> str:
    payload = {"prefix": prefix, **parts}
    return f"{prefix}_{stable_json_hash(payload)[:24]}"


def make_decision_id(
    *,
    chain_id: int,
    block_number: int,
    opportunity_id: str,
    route_id: str,
    mode: str = "",
    rl_state: str = "",
    rl_action: int = -1,
) -> str:
    return _stable_id(
        "decision",
        chain_id=int(chain_id or 0),
        block_number=int(block_number or 0),
        opportunity_id=str(opportunity_id or ""),
        route_id=str(route_id or ""),
        mode=str(mode or ""),
        rl_state=str(rl_state or ""),
        rl_action=int(rl_action or -1),
    )


def make_episode_id(
    *,
    chain_id: int,
    block_number: int,
    opportunity_id: str,
    route_id: str,
    decision_id: str,
) -> str:
    return _stable_id(
        "episode",
        chain_id=int(chain_id or 0),
        block_number=int(block_number or 0),
        opportunity_id=str(opportunity_id or ""),
        route_id=str(route_id or ""),
        decision_id=str(decision_id or ""),
    )


def make_replay_event_id(
    *,
    chain_id: int,
    block_number: int,
    opportunity_id: str,
    route_id: str,
    decision_id: str,
) -> str:
    return _stable_id(
        "replay",
        chain_id=int(chain_id or 0),
        block_number=int(block_number or 0),
        opportunity_id=str(opportunity_id or ""),
        route_id=str(route_id or ""),
        decision_id=str(decision_id or ""),
    )
