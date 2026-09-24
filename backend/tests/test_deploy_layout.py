from pathlib import Path

from victor_ai_bot.pathing import canonical_data_dir




def test_repo_root_has_digitalocean_detectable_files():
    root = Path(__file__).resolve().parents[2]
    assert (root / 'Dockerfile').exists()
    assert (root / 'requirements.txt').exists()
    assert (root / 'Procfile').exists()
    assert (root / '.env.example').exists()


def test_backend_startup_script_exists_and_is_referenced():
    root = Path(__file__).resolve().parents[2]
    script = root / 'backend' / 'scripts' / 'start-server.sh'
    assert script.exists()
    dockerfile = (root / 'backend' / 'Dockerfile').read_text()
    assert 'start-server.sh' in dockerfile


def test_no_nested_backend_backend_data_residue_in_repo():
    root = Path(__file__).resolve().parents[2]
    assert not (root / 'backend' / 'backend').exists()


def test_canonical_data_dir_normalizes_legacy_repo_relative_default(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(root / 'backend')
    assert canonical_data_dir('backend/data') == str(root / 'backend' / 'data')


def test_production_compose_wires_only_supported_shadow_chains():
    root = Path(__file__).resolve().parents[2]
    compose = (root / 'deploy' / 'docker-compose.prod.yml').read_text()
    assert 'VICTOR_MULTI_CONFIGS: /app/backend/config/ethereum.yaml,/app/backend/config/base.yaml,/app/backend/config/arbitrum.yaml' in compose
    assert 'VICTOR_MULTI_MAX_CHAINS: "3"' in compose
    assert 'VICTOR_MULTI_ALLOW_AUTO_ALL: "0"' in compose
    assert 'polygon.yaml' not in compose


def test_l2_opportunity_configs_are_shadow_safe_and_have_stable_universe():
    root = Path(__file__).resolve().parents[2]
    expected = {
        "base.yaml": ("8453", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2"),
        "arbitrum.yaml": ("42161", "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9"),
    }
    for name, (chain_id, usdc, usdt) in expected.items():
        text = (root / "backend" / "config" / name).read_text()
        assert f"chain_id: {chain_id}" in text
        assert f"usdc: '{usdc}'" in text
        assert f"usdt: '{usdt}'" in text
        assert "enable_three_leg_loops: true" in text
        assert "enable_v3_triangular: true" in text
        assert "auto_trading: false" in text
        assert "dry_run: true" in text
        assert "base_borrow_amount: '10000000000000000'" in text
