from __future__ import annotations

import inspect


def _patch_httpx_testclient_compat() -> None:
    try:
        import httpx
    except ImportError:
        return
    try:
        params = inspect.signature(httpx.Client.__init__).parameters
    except (TypeError, ValueError):
        return
    if "app" in params:
        return
    original_init = httpx.Client.__init__

    def patched_init(self, *args, app=None, **kwargs):
        return original_init(self, *args, **kwargs)

    httpx.Client.__init__ = patched_init


_patch_httpx_testclient_compat()
