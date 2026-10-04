from types import SimpleNamespace

from victor_ai_bot.execution_capture.sizing import choose_size


def test_quote_derived_curve_is_already_after_cost_and_can_select_observed_optimum():
    envelope = SimpleNamespace(
        safe_size_curve=[
            SimpleNamespace(size_mult=1.0, expected_profit_usd=12.0, slippage_cost_usd=0.0, interference_penalty_usd=0.0, latency_decay_cost_usd=0.0),
            SimpleNamespace(size_mult=2.0, expected_profit_usd=15.0, slippage_cost_usd=0.0, interference_penalty_usd=0.0, latency_decay_cost_usd=0.0),
        ],
        metadata={"economic_model_source": "quote_derived_size_curve"},
        gas_estimate_usd=10.0,
        liquidity_fragility=0.0,
        expected_profit_usd=15.0,
    )
    score = SimpleNamespace(
        expected_realized_value=10.0,
        success_probability=1.0,
        freshness_probability=1.0,
        interference_probability=0.0,
        venue_quality=1.0,
        failure_cost_estimate=0.0,
    )

    mult, value = choose_size(envelope, score)

    assert mult == 2.0
    assert value == 15.0
