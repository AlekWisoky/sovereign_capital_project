from victor_ai_bot.system_truth import build_system_truth, write_system_truth


def test_system_truth_contains_live_registries(tmp_path):
    truth = build_system_truth()
    assert 'V1_ONLY' in truth['launch_modes']
    assert 'flash_arb' in truth['activation_order']
    assert truth['thin_shell_runtime_py_lines'] < 80
    assert truth['route_count'] > 0
    assert truth['generated_at_ms'] > 0
    assert truth['generated_at_iso'].endswith('Z')
    assert truth['generated_at'] == truth['generated_at_iso']
    assert truth['docs_generated_dir'] == 'docs/generated'
    write_system_truth(out_dir=tmp_path)
    assert (tmp_path / 'system_truth.md').exists()
    assert (tmp_path / 'system_truth.json').exists()


def test_generated_docs_match_live_truth():
    import json
    from pathlib import Path
    truth = build_system_truth()
    docs_truth = json.loads((Path(__file__).resolve().parents[2] / 'docs' / 'generated' / 'system_truth.json').read_text(encoding='utf-8'))
    assert docs_truth['launch_modes'] == truth['launch_modes']
    assert docs_truth['activation_order'] == truth['activation_order']
    assert docs_truth['generated_at'] == docs_truth['generated_at_iso']
    assert docs_truth['route_count'] == truth['route_count']
    assert docs_truth['duplicate_route_count'] == truth['duplicate_route_count']
    assert docs_truth['backend_test_file_count'] == truth['backend_test_file_count']


def test_system_truth_reports_exception_inventory_and_legacy_sizes():
    truth = build_system_truth()
    assert truth['runtime_legacy_lines'] > 0
    assert truth['api_legacy_lines'] > 0
    assert truth['runtime_bundle_definition_count'] == 1
    assert truth['runtime_legacy_broad_except_count'] >= 0
    assert truth['api_legacy_broad_except_count'] >= 0
    assert truth['legacy_broad_except_count'] == truth['broad_exception_inventory']['legacy_total']
    assert truth['backend_broad_except_count'] == truth['broad_exception_inventory']['backend_total']
    assert truth['backend_broad_except_count'] >= truth['legacy_broad_except_count']
    assert truth['legacy_broad_exception_sites'] == truth['broad_exception_inventory']['legacy_sites']
    assert truth['backend_broad_exception_sites'] == truth['broad_exception_inventory']['backend_sites']
    assert {
        'path': 'backend/victor_ai_bot/runtime_services/runtime_tick_iteration_facade.py',
        'lineno': 45,
        'end_lineno': 54,
        'handler_form': 'typed',
        'handler_type': 'Exception',
        'line': 'except Exception as e:',
    } in truth['backend_broad_exception_sites']
