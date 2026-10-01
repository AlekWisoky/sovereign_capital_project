from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ethereum_discovery_has_cross_venue_read_only_sources():
    cfg = yaml.safe_load(
        (REPO_ROOT / "backend" / "config" / "ethereum.yaml").read_text()
    )
    chain = cfg["chain"]

    assert chain["univ3_factory"]
    assert chain["univ3_quoter_v2"]
    assert chain["balancer_vault"]
    assert chain["curve_address_provider"] == "0x0000000022D53366457F9d5E68Ec105046FC4383"
    assert chain["enable_venue_discovery"] is True
    assert int(chain["discovery_pool_max_candidates"]) == 48


def test_ethereum_token_universe_and_borrow_anchor_are_present():
    cfg = yaml.safe_load(
        (REPO_ROOT / "backend" / "config" / "ethereum.yaml").read_text()
    )
    chain = cfg["chain"]
    execution = cfg["execution"]

    universe = {str(token).lower() for token in chain["token_universe"]}
    assert chain["weth"].lower() in universe
    assert chain["usdc"].lower() in universe
    assert chain["usdt"].lower() in universe
    assert "0x6b175474e89094c44da98b954eedeac495271d0f" in universe
    assert "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599" in universe
    assert int(execution["base_borrow_amount"]) > 0


def test_ethereum_discovery_runtime_loader_materializes_venue_settings():
    from victor_ai_bot.config import load_config

    cfg = load_config(str(REPO_ROOT / "backend" / "config" / "ethereum.yaml"))
    chain = cfg.chain

    assert chain.curve_address_provider == "0x0000000022D53366457F9d5E68Ec105046FC4383"
    assert chain.enable_venue_discovery is True
    assert chain.discovery_pool_max_candidates == 48
    assert chain.discovery_log_window_blocks == 50_000
