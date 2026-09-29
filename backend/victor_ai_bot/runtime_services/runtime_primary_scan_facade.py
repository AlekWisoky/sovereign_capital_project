            all_opps = list(best_by_route.values())
            opps2 = [o for o in all_opps if str(getattr(o, "strategy", "")).startswith("two-leg:")]
            opps3 = [o for o in all_opps if str(getattr(o, "strategy", "")).startswith("tri:")]
            other_opps = [
                o for o in all_opps
                if o not in opps2 and o not in opps3
            ]
            opps = list(opps2) + list(opps3) + other_opps
            telemetry["adaptive_size_discovery"] = {
                "enabled": bool(len(adaptive_amounts) > 1),
                "base_amount_in": str(int(amount_in)),
                "amounts_scanned": [str(int(x)) for x in size_amounts],
                "probe_triggered": bool(len(size_amounts) > 1),
                "minimum_opportunities": int(min_opportunities),
                "candidates_before_probe": int(candidates_before_probe),
                "candidates_after_probe": int(candidates_after_probe),
                "probe_candidate_delta": int(candidates_after_probe - candidates_before_probe),
                "distinct_route_ids_before_probe": len({
                    _candidate_route_key(candidate) for candidate in [*base_two, *base_three]
                }),
                "distinct_route_ids_after_probe": len({
                    _candidate_route_key(candidate) for candidate in [*opps2, *opps3, *other_opps]
                }),
                "best_sizing_variants": [
                    {
                        "route_id": _candidate_route_key(candidate),
                        "amount_in": _candidate_amount_in(candidate),
                        "expected_profit_raw": str(getattr(candidate, "expected_profit_raw", "0") or "0"),
                    }
                    for candidate in list(opps)[:80]
                ],
            }
            await self._annotate_canonical_after_fee_usd(
                opps=opps,
                rpc=rpc,
                current_block=int(current_block),