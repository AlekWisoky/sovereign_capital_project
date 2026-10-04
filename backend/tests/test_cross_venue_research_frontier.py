from types import SimpleNamespace

from victor_ai_bot.discovery import DiscoveryManager


def test_observed_liquid_token_enters_research_graph_without_execution_admission(tmp_path):
    anchor = "0x" + "11" * 20
    observed = "0x" + "22" * 20
    unrelated = "0x" + "33" * 20

    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            token_universe=[anchor],
        )
    )
    dm = DiscoveryManager(chain_name="base", data_dir=str(tmp_path))
    dm._observe_candidate_tokens([anchor, observed], source="verified_aerodrome_pool")

    pairs = dm._supported_discovery_pairs(
        cfg,
        [anchor, observed, unrelated],
        [10**18, 10**18, 10**18],
    )

    assert {(a.lower(), b.lower()) for _, a, _, b in pairs} == {
        (anchor.lower(), observed.lower()),
        (anchor.lower(), unrelated.lower()),
    }
    assert observed.lower() not in {
        str(token).lower() for token in cfg.chain.token_universe
    }
    assert observed.lower() in dm.candidate_token_telemetry(cfg)["observed_not_admitted"]
