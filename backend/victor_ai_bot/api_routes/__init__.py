from .admin_routes import router as admin_router
from .advanced import router as advanced_router
from .agents import router as agents_router
from .analytics_routes import router as analytics_router
from .command_center_routes import router as command_center_router
from .engine_routes import router as engine_router
from .evolution import router as evolution_router
from .frontend_routes import router as frontend_router
from .fund_routes import router as fund_router
from .governance_routes import router as governance_router
from .intelligence_routes import router as intelligence_router
from .launch_routes import router as launch_router
from .multichain_routes import router as multichain_router
from .operator_command_routes import router as operator_command_router
from .ops_routes import router as ops_router
from .overlay_routes import router as overlay_router
from .rft import router as rft_router
from .risk_routes import router as risk_router
from .runtime_routes import router as runtime_router
from .strategies import router as strategies_router
from .superstructure_routes import router as superstructure_router
from .system_routes import router as system_router
from .telemetry import router as telemetry_router
from .treasury_extra import router as treasury_router
from .wealth import router as wealth_router
from .withdraw_all_routes import router as withdraw_all_router
from .withdraw_routes import router as withdraw_router

__all__ = [
    "admin_router",
    "advanced_router",
    "agents_router",
    "analytics_router",
    "command_center_router",
    "engine_router",
    "evolution_router",
    "frontend_router",
    "fund_router",
    "governance_router",
    "intelligence_router",
    "launch_router",
    "multichain_router",
    "operator_command_router",
    "ops_router",
    "overlay_router",
    "rft_router",
    "risk_router",
    "runtime_router",
    "strategies_router",
    "superstructure_router",
    "system_router",
    "telemetry_router",
    "treasury_router",
    "wealth_router",
    "withdraw_all_router",
    "withdraw_router",
]
