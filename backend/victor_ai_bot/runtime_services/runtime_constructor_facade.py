from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from typing import Any

from ..anomaly_breakers import AnomalyBreaker
from ..cache import PerBlockCache
from ..circuit_breaker import CircuitBreaker
from ..decision_engine import DecisionEngine
from ..discovery import DiscoveryManager
from ..latency_profiler import LatencyProfiler
from ..models import Metrics
from ..pathing import canonical_data_dir
from ..persistence.db import PersistenceDB
from ..rpc_manager import RpcManager
from ..security.audit import SecurityAuditStore
from ..omar.config import OmarConfig
from ..omar.runtime import OmarRuntime


class RuntimeConstructorFacade:
    """Compatibility facade for base RuntimeBundle constructor bootstrap.

    This isolates the remaining constructor-time base state from
    ``runtime_legacy.py`` while preserving the current attribute contract.
    """

    def _initialize_runtime_constructor_core(self, cfg: Any) -> None:
        self.cfg = cfg
        self.rpc_manager = RpcManager(
            rpc_read=cfg.chain.rpc_read,
            rpc_send=cfg.chain.rpc_send or cfg.chain.rpc_read,
            rpc_private=getattr(cfg.chain, "rpc_private", []),
        )
        self.cache = PerBlockCache()
        self.metrics = Metrics(
            gas_mode=cfg.execution.gas_mode,
            send_mode=cfg.execution.send_mode,
        )
        self._lat = LatencyProfiler(window=int(os.environ.get("VICTOR_LAT_WINDOW", "400")))
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._state_lock = asyncio.Lock()
        self._opps = []
        self._errors = deque(maxlen=int(os.environ.get("VICTOR_ERROR_LOG_MAX", "200")))
        self._ws_clients = []
        self._exec_log = deque(maxlen=int(os.environ.get("VICTOR_EXEC_LOG_MAX", "500")))
        self._last_submitted_block = 0
        self._auto_trading = bool(cfg.execution.auto_trading)
        self._cb = CircuitBreaker.from_env()
        self._anomaly = AnomalyBreaker(window=int(os.environ.get("VICTOR_ANOM_WINDOW", "60")))

        self._receipt_q: asyncio.Queue[str] = asyncio.Queue(
            maxsize=int(os.environ.get("VICTOR_RECEIPT_QUEUE_MAX", "20"))
        )
        self._receipt_task: asyncio.Task | None = None
        self._pending = {}

        data_dir = canonical_data_dir(os.environ.get("VICTOR_DATA_DIR", "backend/data"))
        os.makedirs(data_dir, exist_ok=True)
        self.data_dir = data_dir
        self._db = PersistenceDB(os.path.join(data_dir, "state", "xdv_runtime_state.sqlite3"))
        self._security_audit = SecurityAuditStore(self._db)
        self._decision = DecisionEngine(
            chain_name=cfg.chain.name,
            data_dir=data_dir,
            brain_mode=str(getattr(cfg.execution, "brain_mode", "off") or "off"),
        )

        # OMAR is always constructed so it is a first-class subsystem. It remains
        # inert unless explicitly enabled, preserving existing safe defaults.
        env_enabled = (os.environ.get("VICTOR_ENABLE_OMAR", "") or "").strip() == "1"
        configured = getattr(getattr(cfg, "superstructure", None), "omar", None)
        omar_cfg = configured if isinstance(configured, OmarConfig) else OmarConfig(enabled=env_enabled)
        if env_enabled:
            omar_cfg.enabled = True
        self._omar = OmarRuntime(cfg=omar_cfg, chain_name=cfg.chain.name)
        if bool(omar_cfg.enabled):
            self._omar.start()

        self._discovery = DiscoveryManager(chain_name=cfg.chain.name, data_dir=data_dir)
        self._budget_day = time.strftime("%Y-%m-%d", time.gmtime())
        self._gas_spent_today_wei = 0
        self._pending_gas_est_wei = 0
        self._exec_task: asyncio.Task | None = None
        self._auto_queue = []
        self._auto_queue_block = 0
