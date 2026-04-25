from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict


class _JsonFormatter(logging.Formatter):
    """Small JSON log formatter.

    We keep this dependency-free and fast. When VICTOR_LOG_JSON=1, logs become
    structured JSON on stdout to simplify ops.
    """

    def format(self, record: logging.LogRecord) -> str:
        base: Dict[str, Any] = {
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        # Optional extra fields
        for k, v in record.__dict__.items():
            if k.startswith("_"):
                continue
            if k in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            }:
                continue
            try:
                json.dumps(v)
                base[k] = v
            except (TypeError, ValueError):
                base[k] = str(v)
        return json.dumps(base, separators=(",", ":"), ensure_ascii=False)


def configure_logging() -> None:
    """Configure root logging exactly once.

    Safe defaults:
      - INFO level
      - stdout handler
      - optional JSON formatting
    """

    if getattr(configure_logging, "_configured", False):
        return
    setattr(configure_logging, "_configured", True)

    level = os.environ.get("VICTOR_LOG_LEVEL", "INFO").upper()
    use_json = os.environ.get("VICTOR_LOG_JSON", "0") == "1"

    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    if use_json:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root.addHandler(handler)
