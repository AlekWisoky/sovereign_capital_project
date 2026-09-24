from __future__ import annotations

"""Governed AI inference primitives.

This module is deliberately provider-agnostic at the contract boundary. It is an
advisory inference layer: it cannot authorize execution, sizing, admission, or
capital movement. Providers are selected by bounded capability/health/latency/
cost policy and every result carries provenance.
"""

import asyncio
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Iterable, List, Mapping, Optional


@dataclass(frozen=True)
class AgentRequest:
    agent_id: str
    task: str
    prompt: str
    capability: str = "general"
    max_latency_ms: float = 2_000.0
    max_cost_usd: float = 0.05
    preferred_provider: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentConfidence:
    score: float
    rationale: str = ""
    source: str = "model"


@dataclass(frozen=True)
class AgentCost:
    estimated_usd: float
    input_tokens: int = 0
    output_tokens: int = 0
    currency: str = "USD"


@dataclass(frozen=True)
class AgentLatency:
    elapsed_ms: float
    budget_ms: float
    timed_out: bool = False


@dataclass(frozen=True)
class AgentProvider:
    provider: str
    model: str
    capability: str = "general"
    endpoint: str = ""
    api_key_env: str = ""
    timeout_s: float = 2.0
    cost_per_1k_input_usd: float = 0.0
    cost_per_1k_output_usd: float = 0.0
    enabled: bool = True
    fallback_rank: int = 100


@dataclass(frozen=True)
class AgentEvidence:
    evidence_id: str
    agent_id: str
    task: str
    content: str
    structured: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentDecision:
    ok: bool
    evidence: Optional[AgentEvidence]
    confidence: AgentConfidence
    cost: AgentCost
    latency: AgentLatency
    provider: AgentProvider
    fallback_count: int = 0
    reason_code: str = ""


@dataclass
class _ProviderHealth:
    failures: int = 0
    successes: int = 0
    ema_latency_ms: float = 0.0
    unhealthy_until: float = 0.0


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _tokens(text: str) -> int:
    # Conservative local estimate; exact provider usage remains provenance when supplied.
    return max(1, (len(str(text or "")) + 3) // 4)


class GovernedAIRouter:
    """Selects and calls AI providers without granting system authority."""

    def __init__(self, providers: Iterable[AgentProvider], *, failure_cooldown_s: float = 5.0):
        self.providers = [p for p in providers if p.enabled]
        self.failure_cooldown_s = max(0.5, float(failure_cooldown_s))
        self._health: Dict[str, _ProviderHealth] = {
            self._key(p): _ProviderHealth() for p in self.providers
        }

    @staticmethod
    def _key(provider: AgentProvider) -> str:
        return f"{provider.provider}:{provider.model}"

    def state(self) -> Dict[str, Any]:
        now = time.monotonic()
        return {
            self._key(p): {
                "provider": p.provider,
                "model": p.model,
                "capability": p.capability,
                "healthy": self._health[self._key(p)].unhealthy_until <= now,
                "failures": self._health[self._key(p)].failures,
                "successes": self._health[self._key(p)].successes,
                "ema_latency_ms": round(self._health[self._key(p)].ema_latency_ms, 3),
            }
            for p in self.providers
        }

    def _eligible(self, req: AgentRequest) -> List[AgentProvider]:
        now = time.monotonic()
        out = []
        for p in self.providers:
            if p.capability not in {req.capability, "general"}:
                continue
            h = self._health[self._key(p)]
            if h.unhealthy_until > now:
                continue
            out.append(p)
        return out

    def _rank(self, req: AgentRequest, providers: List[AgentProvider]) -> List[AgentProvider]:
        def score(p: AgentProvider) -> tuple[float, int, str]:
            h = self._health[self._key(p)]
            latency = h.ema_latency_ms or p.timeout_s * 1000.0
            cost = p.cost_per_1k_input_usd + p.cost_per_1k_output_usd
            preferred = 0 if req.preferred_provider and p.provider == req.preferred_provider else 1
            # Hard budgets are filters; ranking then favors observed speed, cost and fallback order.
            return (latency + cost * 100.0, preferred, int(p.fallback_rank))
        return sorted(providers, key=score)

    async def infer(self, req: AgentRequest) -> AgentDecision:
        candidates = self._rank(req, self._eligible(req))
        if not candidates:
            provider = AgentProvider(provider="none", model="none", capability=req.capability, enabled=False)
            return AgentDecision(
                ok=False,
                evidence=None,
                confidence=AgentConfidence(0.0, "no_provider_available", "router"),
                cost=AgentCost(0.0),
                latency=AgentLatency(0.0, req.max_latency_ms),
                provider=provider,
                reason_code="no_provider_available",
            )

        last_reason = "inference_failed"
        for index, provider in enumerate(candidates):
            started = time.perf_counter()
            try:
                text, structured, usage = await self._call_provider(provider, req)
                elapsed = (time.perf_counter() - started) * 1000.0
                if elapsed > float(req.max_latency_ms):
                    raise asyncio.TimeoutError(f"ai_latency_budget_exceeded:{elapsed:.3f}ms")
                input_tokens = int(usage.get("input_tokens") or _tokens(req.prompt))
                output_tokens = int(usage.get("output_tokens") or _tokens(text))
                cost = AgentCost(
                    estimated_usd=(
                        input_tokens * provider.cost_per_1k_input_usd
                        + output_tokens * provider.cost_per_1k_output_usd
                    ) / 1000.0,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                if cost.estimated_usd > float(req.max_cost_usd):
                    raise ValueError("ai_cost_budget_exceeded")
                self._mark_success(provider, elapsed)
                evidence = AgentEvidence(
                    evidence_id=f"ai:{req.agent_id}:{int(time.time_ns())}",
                    agent_id=req.agent_id,
                    task=req.task,
                    content=str(text or ""),
                    structured=dict(structured or {}),
                    provenance={
                        "provider": provider.provider,
                        "model": provider.model,
                        "capability": provider.capability,
                        "fallback_count": index,
                        "latency_ms": round(elapsed, 3),
                        "estimated_cost_usd": round(cost.estimated_usd, 8),
                        "authority": "advisory_evidence_only",
                    },
                )
                confidence = _confidence_from_response(structured)
                return AgentDecision(
                    ok=True,
                    evidence=evidence,
                    confidence=confidence,
                    cost=cost,
                    latency=AgentLatency(elapsed, req.max_latency_ms),
                    provider=provider,
                    fallback_count=index,
                    reason_code="ok",
                )
            except (asyncio.TimeoutError, OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
                elapsed = (time.perf_counter() - started) * 1000.0
                self._mark_failure(provider, elapsed)
                last_reason = str(exc) or "inference_failed"
                continue

        provider = candidates[-1]
        return AgentDecision(
            ok=False,
            evidence=None,
            confidence=AgentConfidence(0.0, last_reason, "router"),
            cost=AgentCost(0.0),
            latency=AgentLatency(float(req.max_latency_ms), req.max_latency_ms, True),
            provider=provider,
            fallback_count=max(0, len(candidates) - 1),
            reason_code=(
                "ai_http_client_unavailable"
                if last_reason == "ai_http_client_unavailable"
                else "all_providers_failed"
            ),
        )

    async def _call_provider(
        self, provider: AgentProvider, req: AgentRequest
    ) -> tuple[str, Dict[str, Any], Dict[str, int]]:
        if provider.provider.lower() != "openai":
            raise ValueError(f"provider_unsupported:{provider.provider}")
        key = (os.environ.get(provider.api_key_env, "") or "").strip()
        if not key:
            raise ValueError("ai_api_key_missing")
        try:
            import aiohttp
        except ImportError as exc:
            raise RuntimeError("ai_http_client_unavailable") from exc
        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": "Return concise research evidence. Do not authorize trades or capital movement."},
                {"role": "user", "content": req.prompt},
            ],
            "temperature": 0.0,
        }
        timeout = aiohttp.ClientTimeout(total=max(0.1, float(provider.timeout_s)))
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                provider.endpoint,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            ) as response:
                if response.status != 200:
                    body = (await response.text())[:160]
                    raise RuntimeError(f"ai_http_{response.status}:{body}")
                obj = await response.json()
        choices = obj.get("choices") if isinstance(obj, dict) else None
        if not choices:
            raise ValueError("ai_response_missing_choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content:
            raise ValueError("ai_response_missing_content")
        usage_raw = obj.get("usage") if isinstance(obj, dict) else {}
        usage = {
            "input_tokens": int((usage_raw or {}).get("prompt_tokens") or 0),
            "output_tokens": int((usage_raw or {}).get("completion_tokens") or 0),
        }
        return str(content).strip(), {}, usage

    def _mark_success(self, provider: AgentProvider, elapsed_ms: float) -> None:
        h = self._health[self._key(provider)]
        h.successes += 1
        h.failures = max(0, h.failures - 1)
        h.ema_latency_ms = (
            float(elapsed_ms) if h.ema_latency_ms <= 0 else 0.75 * h.ema_latency_ms + 0.25 * float(elapsed_ms)
        )

    def _mark_failure(self, provider: AgentProvider, elapsed_ms: float) -> None:
        h = self._health[self._key(provider)]
        h.failures += 1
        h.unhealthy_until = time.monotonic() + self.failure_cooldown_s
        if elapsed_ms > 0:
            h.ema_latency_ms = (
                float(elapsed_ms) if h.ema_latency_ms <= 0 else 0.85 * h.ema_latency_ms + 0.15 * float(elapsed_ms)
            )


def _confidence_from_response(structured: Mapping[str, Any] | None) -> AgentConfidence:
    payload = dict(structured or {})
    try:
        score = _clip(float(payload.get("confidence", 0.65)), 0.0, 1.0)
    except (TypeError, ValueError, OverflowError):
        score = 0.65
    return AgentConfidence(score, str(payload.get("confidence_reason") or "model_output"), "model")
