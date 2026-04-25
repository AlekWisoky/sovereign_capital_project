from __future__ import annotations

"""LLM-mediated Interactive Narrative Layer (LLM-INL) configuration.

LLM-INL is a **non-breaking overlay**. When disabled (default), the runtime
behaves exactly as before.

Design goals:
  - Improve explainability and operator handling.
  - Provide a safe interactive query surface.
  - Keep core engine immutable (no modifications to core execution logic).
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class LLMINLConfig:
    # Master toggle
    enabled: bool = False

    # Global mode flags (metadata)
    system_mode: str = "AUTONOMOUS_MULTI_AGENT"
    architecture_lock: bool = True
    core_commands_immutable: bool = True

    # Section 1: Context memory
    max_narrative_memory: int = 100
    persist_history: bool = True

    # Section 3: Interactive query engine
    interactive_mode: bool = True
    # Admin-only by default. If false, query endpoints can be opened.
    require_admin_for_queries: bool = True

    # Section 4: Adaptive personalization
    explanation_level: str = "STANDARD"  # BASIC | STANDARD | ADVANCED

    # Section 6: Conflict mediation
    conflict_mediation_enabled: bool = True

    # Narrative audit report generator
    audit_enabled: bool = True
    audit_max_bytes: int = 25_000_000

    # Runtime loop tick
    loop_interval_s: float = 1.0

    # Block scan summaries (optional)
    emit_block_summaries: bool = False
    block_summary_interval_blocks: int = 5
    block_summary_min_profit_wei: int = 0

    # LLM integration (optional). When disabled or misconfigured, falls back to
    # template narratives.
    llm_mode: str = "template"  # off | template | llm
    llm_provider: str = "openai"  # openai | (future)
    llm_api_key_env: str = "VICTOR_LLM_API_KEY"
    llm_model: str = "gpt-4o-mini"
    llm_endpoint: str = "https://api.openai.com/v1/chat/completions"
    llm_timeout_s: float = 10.0
    llm_temperature: float = 0.2

    # Data segmentation levels (mirrors FIU-style semantics)
    data_access_levels: List[str] = field(default_factory=lambda: [
        "PUBLIC_ANALYTICS",
        "INTERNAL_STRATEGY",
        "CONFIDENTIAL_SIGNAL",
    ])
    # If strict, CONFIDENTIAL_SIGNAL access is blocked unless agent is GOVERNANCE_AGENT.
    confidentiality_strict: bool = False
