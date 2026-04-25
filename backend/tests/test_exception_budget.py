from pathlib import Path

from victor_ai_bot.repo_inspection import list_broad_exception_handlers


ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = ROOT / 'victor_ai_bot'


def _broad_exception_sites() -> list[dict[str, object]]:
    sites: list[dict[str, object]] = []
    for path in sorted(CODE_ROOT.rglob('*.py')):
        sites.extend(list_broad_exception_handlers(path, relative_to=ROOT))
    sites.sort(key=lambda item: (str(item['path']), int(item['lineno'])))
    return sites


def test_live_backend_has_single_documented_broad_exception_site() -> None:
    sites = _broad_exception_sites()
    assert len(sites) == 1

    site = sites[0]
    assert site['path'] == 'victor_ai_bot/runtime_services/runtime_tick_iteration_facade.py'
    assert site['handler_form'] == 'typed'
    assert site['handler_type'] == 'Exception'
    assert site['line'] == 'except Exception as e:'

    runtime_lines = (ROOT / 'victor_ai_bot' / 'runtime_services' / 'runtime_tick_iteration_facade.py').read_text(encoding='utf-8').splitlines()
    runtime_text = '\n'.join(runtime_lines)
    assert 'Intentional process-boundary containment' in runtime_text
    assert 'last remaining broad catch in live backend code' in runtime_text
    assert 'Fail closed for the current tick' in runtime_text

    lineno = int(site['lineno'])
    next_code_line = None
    for candidate in runtime_lines[lineno:]:
        stripped = candidate.strip()
        if not stripped or stripped.startswith('#'):
            continue
        next_code_line = stripped
        break

    assert next_code_line == 'await self._contain_tick_failure(e)'
