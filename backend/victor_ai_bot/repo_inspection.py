from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List


BroadExceptionSite = Dict[str, Any]


def is_broad_exception_type(node: ast.expr | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in {"Exception", "BaseException"}
    if isinstance(node, ast.Tuple):
        return any(is_broad_exception_type(item) for item in node.elts)
    return False


def list_broad_exception_handlers(
    path: Path, *, relative_to: Path | None = None
) -> List[BroadExceptionSite]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    sites: List[BroadExceptionSite] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or not is_broad_exception_type(node.type):
            continue
        line_text = ""
        if 0 < node.lineno <= len(lines):
            line_text = lines[node.lineno - 1].strip()
        handler_type = ast.get_source_segment(source, node.type) if node.type is not None else None
        handler_form = "bare" if node.type is None else "typed"
        rel_path = str(path.relative_to(relative_to)) if relative_to is not None else str(path)
        sites.append(
            {
                "path": rel_path,
                "lineno": int(node.lineno),
                "end_lineno": int(getattr(node, "end_lineno", node.lineno) or node.lineno),
                "handler_form": handler_form,
                "handler_type": str(handler_type or ""),
                "line": line_text,
            }
        )
    sites.sort(key=lambda item: (str(item["path"]), int(item["lineno"])))
    return sites


def count_broad_exception_handlers(path: Path) -> int:
    return len(list_broad_exception_handlers(path))
