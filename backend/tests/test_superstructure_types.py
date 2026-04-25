import pytest

from victor_ai_bot.superstructure.types import safe_float


def test_safe_float_accepts_numeric_strings():
    assert safe_float("1.25") == pytest.approx(1.25)


def test_safe_float_falls_back_for_invalid_strings():
    assert safe_float("bad", 3.5) == pytest.approx(3.5)


def test_safe_float_does_not_swallow_unexpected_runtime_errors():
    class Explodes:
        def __float__(self):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        safe_float(Explodes())
