from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstitutionalCapitalScalePolicy:
    """USD-denominated capital targets for institutional V1 sizing.

    These values are economic targets, not permission to bypass liquidity,
    profitability, governance, sizing, prime, treasury, or execution gates.
    Raw token amounts must be derived from a live route quote and token decimals.
    """

    baseline_target_usd: float = 250_000.0
    operating_target_usd: float = 500_000.0
    scale_tiers_usd: tuple[float, ...] = (1_000_000.0, 2_500_000.0, 5_000_000.0)
    internal_prime_capacity_target_usd: float = 10_000_000.0

    @property
    def ladder_usd(self) -> tuple[float, ...]:
        return (
            float(self.baseline_target_usd),
            float(self.operating_target_usd),
            *tuple(float(x) for x in self.scale_tiers_usd),
        )

    def requested_notional_usd(self, capital_required_usd: float) -> float:
        """Return the institutional request target without approving execution size."""
        required = max(0.0, float(capital_required_usd or 0.0))
        return max(float(self.baseline_target_usd), required)

    def approved_notional_usd(
        self,
        *,
        requested_notional_usd: float,
        liquidity_cap_usd: float,
        profitability_cap_usd: float,
        governance_cap_usd: float,
        prime_cap_usd: float,
        treasury_cap_usd: float,
    ) -> float:
        """Return the final economic ceiling after independent capital gates."""
        caps = (
            float(requested_notional_usd),
            float(liquidity_cap_usd),
            float(profitability_cap_usd),
            float(governance_cap_usd),
            float(prime_cap_usd),
            float(treasury_cap_usd),
        )
        valid = [max(0.0, value) for value in caps]
        return float(min(valid)) if valid else 0.0


INSTITUTIONAL_V1_POLICY = InstitutionalCapitalScalePolicy()
