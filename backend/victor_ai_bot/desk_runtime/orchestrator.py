from __future__ import annotations

from typing import Any, Dict, Iterable, List


def collect_pod_actions(
    pods: Iterable[Any], opportunities: Dict[str, List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for pod in pods:
        fam = str(getattr(getattr(pod, "contract", None), "family", "") or "")
        out.extend(list(pod.produce(opportunities.get(fam, []))))
    return out
