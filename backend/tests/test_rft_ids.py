from victor_ai_bot.rft.ids import make_decision_id, make_episode_id, make_replay_event_id


def test_ids_are_deterministic_for_same_input():
    d1 = make_decision_id(chain_id=1, block_number=123, opportunity_id="opp", route_id="route", mode="auto", rl_state="s", rl_action=2)
    d2 = make_decision_id(chain_id=1, block_number=123, opportunity_id="opp", route_id="route", mode="auto", rl_state="s", rl_action=2)
    assert d1 == d2

    e1 = make_episode_id(chain_id=1, block_number=123, opportunity_id="opp", route_id="route", decision_id=d1)
    e2 = make_episode_id(chain_id=1, block_number=123, opportunity_id="opp", route_id="route", decision_id=d1)
    assert e1 == e2

    r1 = make_replay_event_id(chain_id=1, block_number=123, opportunity_id="opp", route_id="route", decision_id=d1)
    r2 = make_replay_event_id(chain_id=1, block_number=123, opportunity_id="opp", route_id="route", decision_id=d1)
    assert r1 == r2


def test_ids_change_when_key_inputs_change():
    base = make_decision_id(chain_id=1, block_number=123, opportunity_id="opp", route_id="route", mode="auto", rl_state="s", rl_action=2)
    changed = make_decision_id(chain_id=1, block_number=124, opportunity_id="opp", route_id="route", mode="auto", rl_state="s", rl_action=2)
    assert base != changed
