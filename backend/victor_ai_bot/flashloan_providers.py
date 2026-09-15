from __future__ import annotations

from collections.abc import Iterable


# This registry is the executable-provider authority for the current executor ABI.
# Provider names outside this set are observations/requests only and must never be
# silently converted into an executable provider.
EXECUTABLE_FLASHLOAN_PROVIDERS: tuple[str, ...] = ("aave", "balancer")


def normalize_flashloan_provider(provider: object) -> str:
    """Normalize a provider label without granting executable capability."""
    return str(provider or "").strip().lower()


def is_executable_flashloan_provider(provider: object) -> bool:
    """Return whether the normalized provider has a canonical executor adapter."""
    return normalize_flashloan_provider(provider) in EXECUTABLE_FLASHLOAN_PROVIDERS


def filter_executable_flashloan_providers(
    providers: Iterable[object],
) -> list[str]:
    """Keep only canonical providers, preserving first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for provider in providers:
        normalized = normalize_flashloan_provider(provider)
        if normalized in EXECUTABLE_FLASHLOAN_PROVIDERS and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result
