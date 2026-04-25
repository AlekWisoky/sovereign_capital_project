from __future__ import annotations

import itertools
import json
import os
from json import JSONDecodeError
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Tuple

from .models import CaptureScore, OpportunityEnvelope, SafeSizePoint


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass(frozen=True)
class RoutePlan:
    selected_venues: List[str]
    size_mult: float
    expected_value: float
    total_cost: float
    score: float
    split: List[Dict[str, Any]]
    fallback_tree: List[Dict[str, Any]]
    latency_penalty: float
    competition_penalty: float
    reliability_bonus: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VenueScorecardStore:
    def __init__(self, *, data_dir: str, chain: str):
        self.chain = str(chain)
        self._path = os.path.join(
            data_dir, "execution_capture", f"venue_scorecards_{self.chain}.json"
        )
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._state = self._load()

    def _blank(self) -> Dict[str, Any]:
        return {"items": {}}

    def _coerce_item(self, item: Any) -> Dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        attempts = max(0, int(item.get("attempts") or 0))
        successes = max(0, min(attempts, int(item.get("successes") or 0)))
        return {
            "pair": str(item.get("pair") or ""),
            "size_bucket": str(item.get("size_bucket") or ""),
            "latency_class": str(item.get("latency_class") or ""),
            "venue": str(item.get("venue") or ""),
            "attempts": attempts,
            "successes": successes,
            "realized_edge_usd_sum": float(item.get("realized_edge_usd_sum") or 0.0),
        }

    def _coerce_state(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return self._blank()
        items_raw = data.get("items")
        if not isinstance(items_raw, dict):
            return self._blank()
        items: Dict[str, Dict[str, Any]] = {}
        for key, value in items_raw.items():
            coerced = self._coerce_item(value)
            if coerced is None:
                continue
            canonical_key = self._key(
                pair=str(coerced.get("pair") or ""),
                size_bucket=str(coerced.get("size_bucket") or ""),
                latency_class=str(coerced.get("latency_class") or ""),
                venue=str(coerced.get("venue") or ""),
            )
            items[canonical_key or str(key)] = coerced
        return {"items": items}

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self._path):
            return self._blank()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return self._coerce_state(data)
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()

    def _persist(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def _key(self, *, pair: str, size_bucket: str, latency_class: str, venue: str) -> str:
        return "|".join([str(pair), str(size_bucket), str(latency_class), str(venue)])

    def observe(
        self,
        *,
        pair: str,
        size_bucket: str,
        latency_class: str,
        venue: str,
        success: bool,
        realized_edge_usd: float,
    ) -> None:
        key = self._key(
            pair=pair, size_bucket=size_bucket, latency_class=latency_class, venue=venue
        )
        item = dict((self._state.get("items") or {}).get(key) or {})
        item["pair"] = pair
        item["size_bucket"] = size_bucket
        item["latency_class"] = latency_class
        item["venue"] = venue
        item["attempts"] = int(item.get("attempts") or 0) + 1
        item["successes"] = int(item.get("successes") or 0) + (1 if success else 0)
        item["realized_edge_usd_sum"] = float(item.get("realized_edge_usd_sum") or 0.0) + float(
            realized_edge_usd
        )
        self._state.setdefault("items", {})[key] = item
        self._persist()

    def summary(
        self, *, pair: str, size_bucket: str, latency_class: str, venue: str
    ) -> Dict[str, Any]:
        key = self._key(
            pair=pair, size_bucket=size_bucket, latency_class=latency_class, venue=venue
        )
        item = dict((self._state.get("items") or {}).get(key) or {})
        attempts = int(item.get("attempts") or 0)
        success_rate = (
            float(item.get("successes") or 0) / float(max(1, attempts)) if attempts else 0.65
        )
        edge_mean = (
            float(item.get("realized_edge_usd_sum") or 0.0) / float(max(1, attempts))
            if attempts
            else 0.0
        )
        quality = _clip(
            (0.70 * success_rate) + (0.30 * _clip(0.5 + edge_mean / 10.0, 0.0, 1.0)), 0.1, 1.2
        )
        return {
            "attempts": attempts,
            "success_rate": round(success_rate, 6),
            "mean_edge_usd": round(edge_mean, 6),
            "quality": round(quality, 6),
        }

    def snapshot(self) -> Dict[str, Any]:
        items = []
        for key, value in sorted((self._state.get("items") or {}).items()):
            if isinstance(value, dict):
                items.append(
                    {
                        "key": key,
                        **value,
                        **self.summary(
                            pair=str(value.get("pair") or ""),
                            size_bucket=str(value.get("size_bucket") or ""),
                            latency_class=str(value.get("latency_class") or ""),
                            venue=str(value.get("venue") or ""),
                        ),
                    }
                )
        return {"items": items}


def size_bucket_for(mult: float) -> str:
    if mult <= 0.50:
        return "tiny"
    if mult <= 0.90:
        return "small"
    if mult <= 1.15:
        return "medium"
    return "large"


def latency_class_for(ms: float) -> str:
    if ms <= 450.0:
        return "fast"
    if ms <= 900.0:
        return "moderate"
    return "slow"


def _unique_ordered(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in list(values or []):
        key = str(value or "")
        if not key or key in seen:
            continue
        out.append(key)
        seen.add(key)
    return out


def _venue_score(
    scorecards: VenueScorecardStore | None,
    *,
    pair: str,
    size_bucket: str,
    latency_class: str,
    venue: str,
) -> float:
    if scorecards is None:
        return 0.85
    return float(
        scorecards.summary(
            pair=pair, size_bucket=size_bucket, latency_class=latency_class, venue=venue
        ).get("quality")
        or 0.85
    )


def plan_route(
    *,
    envelope: OpportunityEnvelope,
    capture: CaptureScore,
    telemetry: Dict[str, float],
    latency_pressure: float,
    scorecards: VenueScorecardStore | None = None,
    route_quality: Any | None = None,
    max_subset_size: int = 3,
) -> RoutePlan:
    venues = _unique_ordered(envelope.venues) or ["unknown"]
    pair = "/".join(list(envelope.token_path[:2])) if envelope.token_path else "unknown"
    latency_class = latency_class_for(
        float(
            telemetry.get("lane_avg_latency_ms", telemetry.get("best_latency_ms", 700.0)) or 700.0
        )
    )
    points = list(envelope.safe_size_curve or []) or [
        SafeSizePoint(1.0, envelope.expected_profit_usd, 0.0, 0.0, 0.0)
    ]
    combos: List[Tuple[str, ...]] = []
    for width in range(1, min(max_subset_size, len(venues)) + 1):
        combos.extend(list(itertools.combinations(venues, width)))
    if not combos:
        combos = [(venues[0],)]

    candidates: List[RoutePlan] = []
    for subset in combos:
        subset_list = list(subset)
        split_count = max(1, len(subset_list))
        venue_quality = sum(
            _venue_score(
                scorecards, pair=pair, size_bucket="medium", latency_class=latency_class, venue=v
            )
            for v in subset_list
        ) / float(split_count)
        for point in points[:4]:
            size_bucket = size_bucket_for(float(point.size_mult))
            per_venue_quality = sum(
                _venue_score(
                    scorecards,
                    pair=pair,
                    size_bucket=size_bucket,
                    latency_class=latency_class,
                    venue=v,
                )
                for v in subset_list
            ) / float(split_count)
            split_benefit = 1.0 / (float(split_count) ** 0.5)
            split_slippage = float(point.slippage_cost_usd) * max(0.55, split_benefit)
            gas_cost = float(envelope.gas_estimate_usd) * (1.0 + 0.08 * max(0, split_count - 1))
            failure_cost = float(capture.failure_cost_estimate) * (
                1.0 + max(0.0, 1.0 - per_venue_quality) * 0.5
            )
            freshness_decay = float(point.latency_decay_cost_usd) * (
                1.0 + float(latency_pressure) * 0.75 + 0.05 * max(0, split_count - 1)
            )
            competition_penalty = (
                float(capture.interference_probability)
                * float(point.expected_profit_usd)
                * (0.20 / float(split_count))
            )
            latency_penalty = float(latency_pressure) * float(point.expected_profit_usd) * 0.12
            reliability_bonus = max(
                0.0, (per_venue_quality - 0.75) * float(point.expected_profit_usd) * 0.10
            )
            expected_value = (
                (
                    float(point.expected_profit_usd)
                    * float(capture.success_probability)
                    * float(capture.freshness_probability)
                    * max(0.05, 1.0 - float(capture.interference_probability))
                    * max(0.20, venue_quality)
                )
                - gas_cost
                - split_slippage
                - failure_cost
                - freshness_decay
                - competition_penalty
                - latency_penalty
                + reliability_bonus
            )
            total_cost = (
                gas_cost
                + split_slippage
                + failure_cost
                + freshness_decay
                + competition_penalty
                + latency_penalty
            )
            score = expected_value - total_cost * 0.10
            split = [
                {
                    "venue": v,
                    "share": round(1.0 / float(split_count), 6),
                    "size_mult": round(float(point.size_mult) / float(split_count), 6),
                    "venue_quality": round(
                        _venue_score(
                            scorecards,
                            pair=pair,
                            size_bucket=size_bucket,
                            latency_class=latency_class,
                            venue=v,
                        ),
                        6,
                    ),
                }
                for v in subset_list
            ]
            split_signature = (
                ",".join(f"{row['venue']}:{row['share']}" for row in split) or "default"
            )
            hist_quality = 0.75
            hist_bonus = 0.0
            if route_quality is not None and hasattr(route_quality, "summary"):
                hist = route_quality.summary(
                    route_family=str(envelope.route_family),
                    venue_subset=subset_list,
                    split_signature=split_signature,
                )
                hist_quality = float(hist.get("quality") or hist_quality)
                hist_bonus = max(
                    0.0, (hist_quality - 0.75) * float(point.expected_profit_usd) * 0.08
                )
            expected_value = expected_value + hist_bonus
            score = (
                score
                + hist_bonus
                - max(0.0, 0.75 - hist_quality) * float(point.expected_profit_usd) * 0.05
            )
            candidates.append(
                RoutePlan(
                    selected_venues=subset_list,
                    size_mult=float(point.size_mult),
                    expected_value=round(expected_value, 6),
                    total_cost=round(total_cost, 6),
                    score=round(score, 6),
                    split=split,
                    fallback_tree=[],
                    latency_penalty=round(latency_penalty, 6),
                    competition_penalty=round(competition_penalty, 6),
                    reliability_bonus=round(reliability_bonus + hist_bonus, 6),
                )
            )

    candidates.sort(
        key=lambda x: (
            -float(x.score),
            -float(x.expected_value),
            len(x.selected_venues),
            tuple(x.selected_venues),
            float(x.size_mult),
        )
    )
    best = candidates[0]
    fallback_tree = [c.to_dict() for c in candidates[1:4] if c.expected_value > 0.0]
    return RoutePlan(
        selected_venues=best.selected_venues,
        size_mult=best.size_mult,
        expected_value=best.expected_value,
        total_cost=best.total_cost,
        score=best.score,
        split=best.split,
        fallback_tree=fallback_tree,
        latency_penalty=best.latency_penalty,
        competition_penalty=best.competition_penalty,
        reliability_bonus=best.reliability_bonus,
    )
