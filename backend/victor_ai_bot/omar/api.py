from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException


def build_router(get_runtime):
    router = APIRouter(prefix="/api/omar", tags=["omar"])

    @router.get("/state")
    def state(rt=Depends(get_runtime)) -> Dict[str, Any]:
        return rt.state()

    @router.get("/learning-quality")
    def learning_quality(rt=Depends(get_runtime)) -> Dict[str, Any]:
        """Expose the live-influence learning-quality gate without authority changes."""
        return rt.learning_quality()

    @router.post("/start")
    def start(rt=Depends(get_runtime)):
        if not rt.cfg.enabled:
            raise HTTPException(status_code=400, detail="OMAR disabled by config")
        rt.start()
        return {"ok": True}

    @router.post("/stop")
    def stop(rt=Depends(get_runtime)):
        rt.stop()
        return {"ok": True}

    return router
