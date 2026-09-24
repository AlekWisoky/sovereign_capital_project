from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / "backend" / "config" / name).read_text())


def test_base_and_arbitrum_have_real_venue_endpoints_and_safe_defaults():
    expected = {
        "base.yaml": {
            "chain_id": 8453,
            "weth": "0x4200000000000000000000000000000000000006",
            "quoter": "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
            "factory": "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
            "router": "0x2626664c2603336E57B271c5C0b26F421741e481",
            "aave": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
            "usdc": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "usdt": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
        },
        "arbitrum.yaml": {
            "chain_id": 42161,
            "weth": "0x82aF49447D8A07e3bd95BD0d56f35241523fBab1",
            "quoter": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
            "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984",
            "router": "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
            "aave": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
            "usdc": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
                "usdt": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        },
    }
    for name, want in expected.items():
        cfg = _load(name)
        chain = cfg["chain"]
        assert chain["chain_id"] == want["chain_id"]
        assert chain["weth"] == want["weth"]
        assert chain["univ3_quoter_v2"] == want["quoter"]
        assert chain["univ3_factory"] == want["factory"]
        assert chain["univ3_swap_router"] == want["router"]
        assert chain["aave_v3_pool"] == want["aave"]
        assert chain["balancer_vault"] == "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
        assert chain["curve_address_provider"] == "0x0000000022D53366457F9d5E68Ec105046FC4383"
        assert chain["enable_venue_discovery"] is True
        assert chain["token_universe"] == [want["weth"], want["usdc"], want["usdt"]]
        assert cfg["flags"]["enable_discovery"] is True
        assert cfg["flags"]["enable_curve_autogen"] is True
        assert cfg["flags"]["enable_balancer_autogen"] is True
        assert cfg["execution"]["dry_run"] is True
        assert cfg["execution"]["auto_trading"] is False
        assert cfg["safety"]["max_borrow_amount"] == "0"


def test_polygon_is_removed_from_active_configuration_surface():
    config_root = ROOT / "backend" / "config"
    assert not (config_root / "polygon.yaml").exists()
    assert not (config_root / "presets" / "polygon").exists()
    assert "polygon" not in (ROOT / "mobile" / "src" / "utils" / "chainDefaults.ts").read_text().lower()
    active_config_text = "\n".join(
        p.read_text().lower()
        for p in config_root.rglob("*.yaml")
        if p.is_file()
    )
    assert "polygon" not in active_config_text
