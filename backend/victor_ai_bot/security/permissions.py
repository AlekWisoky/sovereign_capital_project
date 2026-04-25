from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    ADMIN_READ = "admin:read"
    ADMIN_WRITE = "admin:write"
    EXECUTE = "execute"
    GOVERNANCE = "governance"
    TREASURY_WRITE = "treasury:write"
    EVOLUTION_WRITE = "evolution:write"
