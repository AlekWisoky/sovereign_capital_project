import ast
from pathlib import Path

from victor_ai_bot.api import router as api_router
from victor_ai_bot.runtime import MultiRuntimeBundle, RuntimeBundle


ROOT = Path(__file__).resolve().parents[1] / 'victor_ai_bot'


def test_runtime_and_api_are_thin_shells():
    runtime_lines = len((ROOT / 'runtime.py').read_text(encoding='utf-8').splitlines())
    api_lines = len((ROOT / 'api.py').read_text(encoding='utf-8').splitlines())
    assert runtime_lines < 80
    assert api_lines < 80


def test_public_import_surface_survives():
    assert RuntimeBundle is not None
    assert MultiRuntimeBundle is not None
    assert api_router is not None


def test_runtime_legacy_has_single_runtimebundle_definition():
    runtime_legacy = ROOT / 'runtime_legacy.py'
    module = ast.parse(runtime_legacy.read_text(encoding='utf-8'))
    definitions = [
        node for node in module.body if isinstance(node, ast.ClassDef) and node.name == 'RuntimeBundle'
    ]
    assert len(definitions) == 1
