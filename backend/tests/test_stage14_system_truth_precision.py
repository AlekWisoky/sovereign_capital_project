import ast
import json
from pathlib import Path

from victor_ai_bot.system_truth import build_system_truth


def _count_broad_handlers_via_ast(root: Path) -> int:
    total = 0
    for path in (root / 'backend' / 'victor_ai_bot').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            handler_type = node.type
            if handler_type is None:
                total += 1
            elif isinstance(handler_type, ast.Name) and handler_type.id in {'Exception', 'BaseException'}:
                total += 1
            elif isinstance(handler_type, ast.Tuple) and any(
                isinstance(item, ast.Name) and item.id in {'Exception', 'BaseException'}
                for item in handler_type.elts
            ):
                total += 1
    return total


def test_system_truth_reports_exact_broad_exception_inventory():
    root = Path(__file__).resolve().parents[2]
    truth = build_system_truth()
    assert truth['backend_broad_except_count'] == _count_broad_handlers_via_ast(root)


def test_system_truth_exposes_route_inventory_summary_fields():
    truth = build_system_truth()
    assert truth['route_count'] == truth['app_route_count']
    assert truth['route_count_basis'] == 'app_routes'
    assert truth['http_route_count_basis'] == 'http_methods_excluding_head_options'
    assert truth['route_count'] >= truth['http_route_count']
    assert truth['application_route_count'] + truth['framework_route_count'] == truth['http_route_count']
    assert truth['websocket_route_count'] >= 1


def test_generated_docs_match_live_truth_for_route_and_exception_summaries():
    root = Path(__file__).resolve().parents[2]
    docs_truth = json.loads((root / 'docs' / 'generated' / 'system_truth.json').read_text(encoding='utf-8'))
    truth = build_system_truth()
    assert docs_truth['backend_broad_except_count'] == truth['backend_broad_except_count']
    assert docs_truth['route_count'] == truth['route_count']
    assert docs_truth['route_count_basis'] == truth['route_count_basis']
    assert docs_truth['http_route_count'] == truth['http_route_count']
    assert docs_truth['http_route_count_basis'] == truth['http_route_count_basis']
    assert docs_truth['application_route_count'] == truth['application_route_count']
    assert docs_truth['framework_route_count'] == truth['framework_route_count']
    assert docs_truth['app_route_count'] == truth['app_route_count']
    assert docs_truth['websocket_route_count'] == truth['websocket_route_count']
