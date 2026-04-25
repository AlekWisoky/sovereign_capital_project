from __future__ import annotations

from typing import Any, Dict, Iterable

from .models import OpportunityEnvelope


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def evaluate_flashloan_resilience(
    *,
    envelope: OpportunityEnvelope,
    pending_metrics: Dict[str, Any],
    route_plan: Dict[str, Any],
    available_providers: Iterable[str] | None = None,
) -> Dict[str, Any]:
    providers = [str(x) for x in list(available_providers or ["aave", "balancer"]) if str(x)] or [
        "aave"
    ]
    pending_stale = float(pending_metrics.get("stale_probability") or 0.0)
    interference = float(pending_metrics.get("interference_probability") or 0.0)
    worst_case_edge = float(
        pending_metrics.get("worst_case_edge")
        or pending_metrics.get("post_ordering_realized_edge")
        or 0.0
    )
    selected_venues = [str(x) for x in list(route_plan.get("selected_venues") or []) if str(x)]
    scenarios = list(pending_metrics.get("scenarios") or [])
    scenario_pressure = (
        sum(float(x.get("ordering_mass") or 0.0) for x in scenarios[:3])
        / float(max(1, min(3, len(scenarios))))
        if scenarios
        else 0.0
    )
    venue_distortion = _clip(
        float(envelope.liquidity_fragility) * 0.45
        + pending_stale * 0.22
        + scenario_pressure * 0.18
        + float(len(selected_venues)) * 0.04,
        0.0,
        1.0,
    )
    race_penalty = _clip(
        interference * 0.48
        + scenario_pressure * 0.22
        + max(0.0, 0.82 - envelope.simulation_confidence) * 0.22
        + venue_distortion * 0.18,
        0.0,
        1.0,
    )
    adv_leg = {
        str(x.get("venue") or ""): dict(x)
        for x in list(pending_metrics.get("leg_risk") or [])
        if isinstance(x, dict)
    }
    leg_states = []
    for venue in list(envelope.venues or []):
        selected = venue in selected_venues or not selected_venues
        adv = adv_leg.get(venue, {})
        venue_overlap = any(
            venue in list(s.get("venues") or [])
            for s in list(pending_metrics.get("clusters") or [])
        )
        leg_distortion = _clip(
            venue_distortion
            + (0.16 if venue_overlap else 0.0)
            + float(adv.get("distortion") or 0.0) * 0.35
            + (0.08 if not selected else 0.0),
            0.0,
            1.0,
        )
        viable = bool(selected and leg_distortion < 0.72 and worst_case_edge > 0.0)
        fallback_venues = [
            str(v) for v in list(selected_venues or envelope.venues) if str(v) and str(v) != venue
        ][:2]
        leg_states.append(
            {
                "venue": venue,
                "selected": selected,
                "distortion": round(leg_distortion, 6),
                "viable": viable,
                "pending_fragile": bool(adv.get("fragile")),
                "fallback_venues": fallback_venues,
            }
        )
    invalidation = bool(
        race_penalty >= 0.82
        or worst_case_edge <= 0.0
        or any(not bool(x["viable"]) and bool(x["selected"]) for x in leg_states)
    )
    preferred = sorted(providers, key=lambda p: (0 if p == "aave" else 1, p))
    provider_scores = []
    for idx, provider in enumerate(preferred):
        score = _clip(1.0 - race_penalty * 0.35 - venue_distortion * 0.22 - idx * 0.08, 0.05, 1.0)
        provider_scores.append({"provider": provider, "score": round(score, 6)})
    provider_scores.sort(key=lambda x: (-float(x["score"]), str(x["provider"])))
    fallback = (
        provider_scores[1]["provider"]
        if len(provider_scores) > 1
        else provider_scores[0]["provider"]
    )
    chosen_provider = provider_scores[0]["provider"]
    return {
        "provider_priority": [x["provider"] for x in provider_scores],
        "provider_scores": provider_scores,
        "fallback_provider": fallback,
        "selected_provider": chosen_provider,
        "reserve_distortion": round(venue_distortion, 6),
        "race_penalty": round(race_penalty, 6),
        "leg_states": leg_states,
        "searcher_invalidation": invalidation,
        "require_fallback_tree": bool(invalidation or venue_distortion >= 0.50),
        "route_viable": not invalidation,
        "route_mutation_required": bool(
            any(bool(x["pending_fragile"]) for x in leg_states) or venue_distortion >= 0.40
        ),
        "reason_codes": [
            code
            for code, ok in [
                ("reserve_distortion", venue_distortion >= 0.50),
                ("ordering_race", race_penalty >= 0.60),
                ("competed_out", worst_case_edge <= 0.0),
                (
                    "leg_degradation",
                    any(not bool(x["viable"]) and bool(x["selected"]) for x in leg_states),
                ),
                ("pending_fragility", any(bool(x["pending_fragile"]) for x in leg_states)),
            ]
            if ok
        ],
    }
