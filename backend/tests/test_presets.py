from victor_ai_bot.presets import list_presets, get_preset

def test_list_presets_has_ethereum():
    p = list_presets()
    assert "ethereum" in p
    assert "default" in p["ethereum"]

def test_get_preset_default():
    j = get_preset("ethereum", "default")
    assert isinstance(j, dict)
