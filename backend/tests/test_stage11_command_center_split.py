from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.command_center_service import CommandCenterService


class _CC:
    def __init__(self):
        self.controls = SimpleNamespace(paused=False, control_mode='auto')
        self.audit = SimpleNamespace(tail=lambda limit=200: [])
    def set_controls(self, patch, actor='operator', reason=''):
        for k, v in patch.items():
            setattr(self.controls, k, v)
        return {'ok': True, 'patch': patch, 'reason': reason}


class _RT:
    def __init__(self):
        self._cc = _CC()
        self.calls = []
    def set_settings(self, **kwargs):
        self.calls.append(kwargs)


def test_command_center_service_applies_pause():
    rt = _RT()
    result = CommandCenterService().apply_controls(rt, {'patch': {'controlMode': 'view_only'}, 'reason': 'pause'})
    assert result.ok is True
    assert rt.calls[-1]['auto_trading'] is False
