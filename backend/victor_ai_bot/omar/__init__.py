"""OMAR-style unified multi-role self-play training overlay.

Non-breaking overlay:
- Does NOT change core trading/MEV logic.
- Provides optional offline/self-play training loop and metrics.
- Integrates with Governance (GMAO) and Superstructure via wrappers.
"""

from .config import OmarConfig
from .runtime import OmarRuntime
