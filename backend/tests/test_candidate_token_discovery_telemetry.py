from types import SimpleNamespace

from victor_ai_bot.discovery import DiscoveryManager


def test_candidate_token_observation_is_read_only_and_respects_admission_boundary(tmp_path):
    manager = DiscoveryManager(chain_name="test", data_dir=str(tmp_path))
    admitted = "0x" + "11" * 20
    unadmitted = "0x" + "22" * 20

    manager._observe_candidate_tokens(
        [admitted, unadmitted],
        source="balancer_pool_candidate",
    )

    cfg = SimpleNamespace(
        chain=SimpleNamespace(token_universe=[admitted]),
    )
    telemetry = manager.candidate_token_telemetry(cfg)

    assert telemetry["execution_universe"] == [admitted]
    assert telemetry["observed_tokens"] == sorted([admitted, unadmitted])
    assert telemetry["observed_not_admitted"] == [unadmitted]
    assert telemetry["observed_not_admitted_count"] == 1
    assert telemetry["admission_mutated"] is False
    assert telemetry["sources"][unadmitted] == ["balancer_pool_candidate"]


def test_candidate_token_observation_hard_cap_does_not_expand_execution_universe(tmp_path):
    manager = DiscoveryManager(chain_name="test", data_dir=str(tmp_path))
    manager._candidate_token_observation_cap = 2
    tokens = ["0x" + f"{i:040x}" for i in range(1, 4)]

    manager._observe_candidate_tokens(tokens, source="curve_pool_candidate")

    cfg = SimpleNamespace(chain=SimpleNamespace(token_universe=[tokens[0]]))
    telemetry = manager.candidate_token_telemetry(cfg)

    assert telemetry["observed_count"] == 2
    assert telemetry["observation_cap"] == 2
    assert telemetry["observation_truncated"] is True
    assert tokens[0] in telemetry["execution_universe"]
    assert tokens[1] in telemetry["observed_not_admitted"]


def test_research_frontier_prefers_cross_venue_observations_and_remains_read_only(tmp_path, monkeypatch):
    manager = DiscoveryManager(chain_name="base", data_dir=str(tmp_path))
    tokens = ["0x" + f"{i:040x}" for i in range(1, 19)]
    manager._candidate_token_observation_cap = 32
    for token in tokens:
        manager._observe_candidate_tokens([token], source="univ3_pool_candidate")
    manager._observe_candidate_tokens([tokens[0]], source="aerodrome_pool_candidate")
    manager._observe_candidate_tokens([tokens[1]], source="slipstream_pool_candidate")
    monkeypatch.setenv("VICTOR_DISCOVERY_FRONTIER_TOKEN_CAP", "16")

    anchor = "0x" + "aa" * 20
    cfg = SimpleNamespace(chain=SimpleNamespace(token_universe=[anchor]))
    frontier = manager._research_frontier_tokens(cfg)

    assert anchor in frontier
    assert tokens[0] in frontier
    assert tokens[1] in frontier
    assert len(frontier) == 17
    assert anchor not in manager._candidate_tokens_observed
