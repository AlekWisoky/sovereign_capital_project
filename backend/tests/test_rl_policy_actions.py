import os
import tempfile

from victor_ai_bot.rl_policy import RlPolicy


def test_rl_actions_expanded_and_persistable():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "rl.json")
        rl = RlPolicy(path=path)
        s = rl.bucket_state(margin_ratio=0.002, gas_ratio=0.0003, has_curve=0, has_balancer=0, legs=2)
        idx, act, qv = rl.select(s, force_conservative=True)
        assert act.gas_mode in {"standard", "fast", "instant"}
        assert 0.0 < act.size_mult <= 1.0
        assert act.borrow_mult in {0.75, 1.0, 1.5, 2.0}
        rl.update(s, idx, 1.0)
        rl.save()
        rl2 = RlPolicy(path=path)
        assert rl2.summary()["actions"]
