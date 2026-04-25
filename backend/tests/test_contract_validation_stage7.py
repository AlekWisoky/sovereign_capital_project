from pathlib import Path


def test_contract_validation_helper_exists():
    root = Path(__file__).resolve().parents[2]
    helper = root / 'scripts' / 'verify_contracts.sh'
    assert helper.exists()
    content = helper.read_text(encoding='utf-8')
    assert 'forge test -q' in content
