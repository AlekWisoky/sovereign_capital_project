import asyncio
from collections import Counter
from types import SimpleNamespace

import pytest

import victor_ai_bot.arb_engine as arb
from victor_ai_bot.quote_diagnostics import classify_quote_error, record_quote_failure


def test_quote_error_classes_are_stable_and_non_sensitive():
    assert classify_quote_error({"code": -32000, "message": "execution reverted: pool"}) == "rpc_revert"
    assert classify_quote_error({"code": 429, "message": "rate limit"}) == "rpc_rate_limited"
    assert classify_quote_error({"code": -32601, "message": "method not found"}) == "rpc_method_unsupported"
    assert classify_quote_error("timeout while reading") == "rpc_timeout"


def test_quote_failure_counter_is_observational():
    diagnostics = {}
    record_quote_failure(diagnostics, "rpc_revert")
    record_quote_failure(diagnostics, "rpc_revert")
    assert diagnostics["failure_reasons"] == Counter({"rpc_revert": 2})


def test_curve_fallback_telemetry_is_not_execution_authority():
    diagnostics = {"fallback_attempts": 3, "fallback_successes": 2}
    assert diagnostics["fallback_successes"] <= diagnostics["fallback_attempts"]

def test_http_status_errors_map_to_provider_classes():
    assert classify_quote_error({"code": 429, "message": "http_status_429"}) == "rpc_rate_limited"
    assert classify_quote_error({"code": 503, "message": "http_status_503"}) == "rpc_error_503"


class _NoCache:
    def get(self, _key):
        return None

    def set(self, _key, _value):
        return None


def _univ3_edge():
    return arb.Edge(
        "univ3",
        "0x" + "11" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        {"fee": 3000},
    )


@pytest.mark.asyncio
async def test_quote_batch_accumulates_failure_reasons_across_batches(monkeypatch):
    async def failed_batch(*args, **kwargs):
        return [None]

    monkeypatch.setattr(arb, "quote_exact_input_single_batch", failed_batch)
    cfg = SimpleNamespace(chain=SimpleNamespace(univ3_quoter_v2="0x" + "44" * 20))
    metrics = {}
    cache = _NoCache()
    edge = _univ3_edge()

    await arb.quote_edges_batch(object(), cfg, cache, [edge], 100, metrics=metrics)
    await arb.quote_edges_batch(object(), cfg, cache, [edge], 101, metrics=metrics)

    assert metrics["quote_requests"] == 2
    assert metrics.get("quote_successes", 0) == 0
    assert metrics["quote_failure_reasons"]["unknown_quote_failure"] == 2
    assert metrics["quote_attempts_by_family"]["univ3"] == 2
    assert metrics["quote_network_requests_by_family"]["univ3"] == 2
    assert metrics["quote_failures_by_family"]["univ3"] == 2


@pytest.mark.asyncio
async def test_quote_batch_attributes_constant_product_failures(monkeypatch):
    edge = arb.Edge(
        "constant_product",
        "0x" + "11" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        {
            "venue_name": "uniswap_v2",
            "factory": "0x" + "44" * 20,
            "pool": "0x" + "55" * 20,
        },
    )

    async def failed_batch(*args, **kwargs):
        return [None]

    monkeypatch.setattr(arb, "quote_constant_product_many", failed_batch)
    cfg = SimpleNamespace(chain=SimpleNamespace())
    metrics = {}
    out = await arb.quote_edges_batch(
        object(), cfg, _NoCache(), [edge], 100, metrics=metrics
    )

    assert out[arb.edge_key(edge)] is None
    assert metrics["quote_requests"] == 1
    assert metrics["quote_failure_reasons"]["unknown_quote_failure"] == 1
    assert metrics["quote_attempts_by_family"]["uniswap_v2"] == 1
    assert metrics["quote_network_requests_by_family"]["uniswap_v2"] == 1
    assert metrics["quote_failures_by_family"]["uniswap_v2"] == 1


@pytest.mark.asyncio
async def test_missing_quote_adapter_is_counted_as_failure_not_network_request():
    metrics = {}
    edge = _univ3_edge()
    cfg = SimpleNamespace(chain=SimpleNamespace())
    out = await arb.quote_edges_batch(
        object(), cfg, _NoCache(), [edge], 100, metrics=metrics
    )

    assert out[arb.edge_key(edge)] is None
    assert metrics["quote_requests"] == 1
    assert metrics["quote_attempts_by_family"]["univ3"] == 1
    assert metrics.get("quote_network_requests_by_family", {}) == {}
    assert metrics["quote_failures_by_family"]["univ3"] == 1
    assert metrics["quote_adapter_unavailable_by_family"]["univ3"] == 1
    assert metrics["quote_failure_reasons"]["quote_adapter_unavailable"] == 1


@pytest.mark.asyncio
async def test_concurrent_quote_batches_attribute_failures_using_local_success_counts(monkeypatch):
    async def mixed_batch(_rpc, _quoter, reqs, **kwargs):
        amount_in = int(reqs[0][3])
        if amount_in == 100:
            return [SimpleNamespace(amount_out=110, gas_estimate=1)]
        await asyncio.sleep(0.02)
        return [None]

    monkeypatch.setattr(arb, "quote_exact_input_single_batch", mixed_batch)
    cfg = SimpleNamespace(chain=SimpleNamespace(univ3_quoter_v2="0x" + "44" * 20))
    metrics = {}
    edge = _univ3_edge()
    rpc = object()
    cache = _NoCache()

    await asyncio.gather(
        arb.quote_edges_batch(rpc, cfg, cache, [edge], 100, metrics=metrics),
        arb.quote_edges_batch(rpc, cfg, cache, [edge], 101, metrics=metrics),
    )

    assert metrics["quote_requests"] == 2
    assert metrics["quote_successes"] == 1
    assert metrics["quote_failure_reasons"]["unknown_quote_failure"] == 1
    assert metrics["quote_successes_by_family"]["univ3"] == 1
    assert metrics["quote_failures_by_family"]["univ3"] == 1


@pytest.mark.asyncio
async def test_one_venue_batch_failure_does_not_abort_later_families(monkeypatch):
    aerodrome = arb.Edge(
        "aerodrome",
        "0x" + "11" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        {"stable": False, "factory": "0x" + "44" * 20},
    )
    slipstream = arb.Edge(
        "slipstream",
        "0x" + "55" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        {"tick_spacing": 60, "factory": "0x" + "66" * 20},
    )
    balancer = arb.Edge(
        "balancer",
        "0x" + "77" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        {"pool_id": "0x" + "88" * 32},
    )
    later_family_called = {"balancer": False}

    async def broken_aerodrome(*args, **kwargs):
        raise RuntimeError("provider batch failed")

    async def short_slipstream_batch(*args, **kwargs):
        return []

    async def successful_balancer(*args, **kwargs):
        later_family_called["balancer"] = True
        return [SimpleNamespace(amount_out=120)]

    monkeypatch.setattr(arb, "quote_aerodrome_many", broken_aerodrome)
    monkeypatch.setattr(arb, "quote_slipstream_many", short_slipstream_batch)
    monkeypatch.setattr(arb, "quote_balancer_given_in_many", successful_balancer)
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            aerodrome_router="0x" + "99" * 20,
            slipstream_quoter_v2="0x" + "aa" * 20,
            balancer_vault="0x" + "bb" * 20,
        )
    )
    metrics = {}
    out = await arb.quote_edges_batch(
        object(), cfg, _NoCache(), [aerodrome, slipstream, balancer], 100,
        metrics=metrics,
    )

    assert out[arb.edge_key(aerodrome)] is None
    assert out[arb.edge_key(slipstream)] is None
    assert out[arb.edge_key(balancer)][0] == 120
    assert later_family_called["balancer"] is True
    assert metrics["quote_attempts_by_family"] == {
        "aerodrome": 1, "slipstream": 1, "balancer": 1,
    }
    assert metrics["quote_successes_by_family"] == {"balancer": 1}
    assert metrics["quote_failures_by_family"] == {
        "aerodrome": 1, "slipstream": 1,
    }
    assert metrics["quote_failure_reasons"]["quote_batch_exception_aerodrome"] == 1
    assert metrics["quote_failure_reasons"]["quote_batch_missing_results_slipstream"] == 1
    assert metrics["quote_failure_reasons_by_adapter"] == {
        "aerodrome": {"quote_batch_exception_aerodrome": 1},
        "slipstream": {"quote_batch_missing_results_slipstream": 1},
    }


@pytest.mark.asyncio
async def test_cancelled_quote_batch_only_counts_dispatched_family(monkeypatch):
    aerodrome = arb.Edge(
        "aerodrome",
        "0x" + "11" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        {"stable": False, "factory": "0x" + "44" * 20},
    )
    balancer = arb.Edge(
        "balancer",
        "0x" + "55" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        {"pool_id": "0x" + "66" * 32},
    )
    started = asyncio.Event()

    async def blocked_aerodrome(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    async def should_not_run(*args, **kwargs):
        raise AssertionError("later venue must not be counted as dispatched")

    monkeypatch.setattr(arb, "quote_aerodrome_many", blocked_aerodrome)
    monkeypatch.setattr(arb, "quote_balancer_given_in_many", should_not_run)
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            aerodrome_router="0x" + "77" * 20,
            balancer_vault="0x" + "88" * 20,
        )
    )
    metrics = {}
    task = asyncio.create_task(
        arb.quote_edges_batch(
            object(), cfg, _NoCache(), [aerodrome, balancer], 100,
            metrics=metrics,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert metrics["quote_requests"] == 1
    assert metrics["quote_cancelled"] == 1
    assert metrics["quote_attempts_by_family"] == {"aerodrome": 1}
    assert metrics["quote_network_requests_by_family"] == {"aerodrome": 1}
    assert metrics["quote_cancelled_by_family"] == {"aerodrome": 1}
    assert metrics.get("quote_successes_by_family", {}) == {}
    assert metrics.get("quote_failures_by_family", {}) == {}
    assert "balancer" not in metrics["quote_attempts_by_family"]


@pytest.mark.asyncio
async def test_malformed_balancer_edge_is_local_failure_and_does_not_count_network(monkeypatch):
    valid = arb.Edge(
        "balancer",
        "0x" + "77" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        {"pool_id": "0x" + "88" * 32},
    )
    malformed = arb.Edge(
        "balancer",
        "0x" + "77" * 20,
        "0x" + "22" * 20,
        "0x" + "33" * 20,
        {"pool_id": "0x1234"},
    )

    async def quote_valid_only(_rpc, _vault, reqs, diagnostics=None):
        assert len(reqs) == 1
        assert reqs[0][0] == valid.params["pool_id"]
        return [SimpleNamespace(amount_out=120)]

    monkeypatch.setattr(arb, "quote_balancer_given_in_many", quote_valid_only)
    cfg = SimpleNamespace(chain=SimpleNamespace(balancer_vault="0x" + "77" * 20))
    metrics = {}
    out = await arb.quote_edges_batch(
        object(), cfg, _NoCache(), [malformed, valid], 100, metrics=metrics
    )

    assert out[arb.edge_key(malformed)] is None
    assert out[arb.edge_key(valid)][0] == 120
    assert metrics["quote_requests"] == 2
    assert metrics["quote_attempts_by_family"] == {"balancer": 2}
    assert metrics["quote_network_requests_by_family"] == {"balancer": 1}
    assert metrics["quote_successes_by_family"] == {"balancer": 1}
    assert metrics["quote_failures_by_family"] == {"balancer": 1}
    assert metrics["quote_failure_reasons"]["invalid_balancer_request"] == 1
    assert metrics["quote_failure_reasons_by_adapter"] == {
        "balancer": {"invalid_balancer_request": 1}
    }
