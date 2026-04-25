import logging

from victor_ai_bot.logging_utils import _JsonFormatter


class _BadRepr:
    def __str__(self) -> str:
        return "<bad-repr>"


class _Circular:
    def __init__(self) -> None:
        self.me = self


def _make_record(**extras):
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=123,
        msg="hello",
        args=(),
        exc_info=None,
    )
    for k, v in extras.items():
        setattr(record, k, v)
    return record


def test_json_formatter_keeps_json_serializable_extras():
    fmt = _JsonFormatter()
    record = _make_record(order_id="abc", amount=12.5, tags=["x", "y"])
    out = fmt.format(record)
    assert '"order_id":"abc"' in out
    assert '"amount":12.5' in out
    assert '"tags":["x","y"]' in out


def test_json_formatter_falls_back_for_type_error_extra():
    fmt = _JsonFormatter()
    record = _make_record(problematic=_BadRepr())
    out = fmt.format(record)
    assert '"problematic":"<bad-repr>"' in out


def test_json_formatter_falls_back_for_value_error_extra():
    fmt = _JsonFormatter()
    record = _make_record(problematic=_Circular())
    out = fmt.format(record)
    assert '"problematic":"' in out
