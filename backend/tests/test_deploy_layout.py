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
