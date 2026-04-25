from pathlib import Path

from victor_ai_bot.verification_report import build_verification_report, write_verification_report


def test_verification_report_contains_generated_inventory(tmp_path):
    report = build_verification_report()
    assert report['backend']['test_file_count'] >= 1
    assert report['mobile']['test_file_count'] >= 1
    assert report['contracts']['test_file_count'] >= 1
    assert report['runtime_surface']['route_count'] > 0
    assert report['runtime_surface']['backend_broad_except_count'] >= 0
    assert report['generator'] == 'scripts/render_verification_report.py'
    write_verification_report(out_dir=tmp_path)
    assert (tmp_path / 'verification_report.json').exists()
    assert (tmp_path / 'verification_report.md').exists()


def test_generated_verification_docs_match_live_report():
    import json

    report = build_verification_report()
    docs_report = json.loads(
        (Path(__file__).resolve().parents[2] / 'docs' / 'generated' / 'verification_report.json').read_text(encoding='utf-8')
    )
    assert docs_report['backend']['test_file_count'] == report['backend']['test_file_count']
    assert docs_report['mobile']['test_file_count'] == report['mobile']['test_file_count']
    assert docs_report['contracts']['test_file_count'] == report['contracts']['test_file_count']
    assert docs_report['runtime_surface']['route_count'] == report['runtime_surface']['route_count']
    assert docs_report['static_analysis']['mypy']['targets'] == report['static_analysis']['mypy']['targets']
