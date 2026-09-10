from victor_ai_bot.aqe.mev.search_engine import MEVSearchEngine


def test_heuristic_mev_candidates_are_observe_only_until_simulation_exists():
    rows = MEVSearchEngine().search(
        mev_state={
            "sample_pending": [
                {
                    "hash": "0x1",
                    "to": "0xrouter",
                    "value_wei": 5 * 10**18,
                    "tags": ["dex_like"],
                    "sel": "0xabcdef12",
                }
            ],
            "high_risk_ratio": 0.2,
        },
        base_opportunities=[],
    )

    assert rows
    assert all(row.lifecycle_eligibility == "observe_only" for row in rows)
    assert all(row.policy_eligibility == "observe_only" for row in rows)
    assert all(row.metadata.get("economics_status") == "heuristic_non_authoritative" for row in rows)
