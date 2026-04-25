from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OperatorPolicy:
    public_mode_mutations_disabled: bool = True
    require_admin_for_sensitive_reads: bool = False
    fail_closed_on_telemetry_errors: bool = True
