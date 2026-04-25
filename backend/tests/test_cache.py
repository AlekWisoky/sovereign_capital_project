
from victor_ai_bot.cache import PerBlockCache

def test_cache_resets_per_block():
    c = PerBlockCache()
    c.reset_if_new_block(1, 100)
    c.set("k", 1)
    assert c.get("k") == 1
    c.reset_if_new_block(1, 101)
    assert c.get("k") is None
