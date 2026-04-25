import math
from typing import Any, Mapping

JS_SAFE_MAX = 2**53 - 1
JS_SAFE_MIN = -(2**53 - 1)

_BIGINT_KEY_HINTS = (
    "wei",
    "amount",
    "reserve",
    "profit",
    "gas",
    "fee",
    "minout",
    "min_out",
    "liquidity",
    "sqrt",
    "price",
    "balance",
    "nonce",
    "value",
    "delta",
    "cap",
)


def _should_stringify_int(key: str | None, n: int) -> bool:
    if n > JS_SAFE_MAX or n < JS_SAFE_MIN:
        return True
    if key:
        lk = key.lower()
        return any(h in lk for h in _BIGINT_KEY_HINTS)
    return False


def to_json_safe(obj: Any, *, _key: str | None = None) -> Any:
    if isinstance(obj, Mapping):
        return {str(k): to_json_safe(v, _key=str(k)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v, _key=_key) for v in obj]
    if isinstance(obj, (bytes, bytearray)):
        return "0x" + bytes(obj).hex()
    if isinstance(obj, int) and not isinstance(obj, bool):
        return str(obj) if _should_stringify_int(_key, obj) else obj
    if isinstance(obj, float):
        if math.isfinite(obj):
            return obj
        return None
    return obj


def json_safe(obj: Any) -> Any:
    return to_json_safe(obj)
