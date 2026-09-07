from victor_ai_bot.jsonsafe import to_json_safe


def test_to_json_safe_breaks_mapping_cycles_without_recursing_forever():
    payload = {}
    payload["self"] = payload

    assert to_json_safe(payload) == {"self": None}


def test_to_json_safe_breaks_list_cycles_without_recursing_forever():
    payload = []
    payload.append(payload)

    assert to_json_safe(payload) == [None]


def test_to_json_safe_preserves_shared_noncyclic_containers():
    shared = {"value": 7}
    payload = {"left": shared, "right": shared}

    assert to_json_safe(payload) == {
        "left": {"value": 7},
        "right": {"value": 7},
    }
