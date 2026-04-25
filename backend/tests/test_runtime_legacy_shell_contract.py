import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'victor_ai_bot'
RUNTIME_LEGACY = ROOT / 'runtime_legacy.py'


def _class_def(name: str) -> ast.ClassDef:
    module = ast.parse(RUNTIME_LEGACY.read_text(encoding='utf-8'))
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f'missing class {name}')


def test_runtime_legacy_declares_compatibility_shell_docstring_and_exports():
    source = RUNTIME_LEGACY.read_text(encoding='utf-8')
    assert 'Compatibility shell for runtime bundle construction and entry wrappers.' in source
    assert '__all__ = ["RuntimeBundle", "MultiRuntimeBundle"]' in source


def test_runtime_legacy_runtimebundle_only_exposes_shell_methods():
    runtimebundle = _class_def('RuntimeBundle')
    methods = [
        node.name
        for node in runtimebundle.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert methods == ['dep', '__init__', '_loop', '_execute_auto']


def test_runtime_legacy_multiruntimebundle_only_exposes_shell_methods():
    multiruntime = _class_def('MultiRuntimeBundle')
    methods = [
        node.name
        for node in multiruntime.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert methods == ['dep', '__init__', 'cfg', 'chains']


def test_runtime_legacy_remains_small_shell_module():
    line_count = len(RUNTIME_LEGACY.read_text(encoding='utf-8').splitlines())
    assert line_count <= 230
