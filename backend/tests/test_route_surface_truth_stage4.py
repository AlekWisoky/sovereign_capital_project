from __future__ import annotations

from collections import Counter

from victor_ai_bot.server import app
from victor_ai_bot.system_truth import build_system_truth


def test_mounted_route_surface_has_no_duplicate_method_path_pairs():
    items = []
    for route in app.routes:
        path = getattr(route, 'path', '')
        methods = [m for m in list(getattr(route, 'methods', []) or []) if m not in {'HEAD', 'OPTIONS'}]
        for method in methods:
            items.append((method, path))
    counts = Counter(items)
    dupes = [k for k, v in counts.items() if v > 1]
    assert dupes == []


def test_system_truth_reports_duplicates_and_flat_timestamp_fields():
    truth = build_system_truth()
    assert truth['route_count'] > 0
    assert truth['duplicate_route_count'] == 0
    assert truth['generated_at_ms'] > 0
    assert truth['generated_at_iso'].endswith('Z')
    assert isinstance(truth['runtime_services'], list)
    assert isinstance(truth['api_route_modules'], list)
    assert truth['duplicate_route_policy'] == 'deduplicated_mount_surface'
