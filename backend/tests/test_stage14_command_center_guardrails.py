from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.command_center_service import CommandCenterService


class _CC:
    def __init__(
        self,
        *,
        paused: bool = True,
        control_mode: str = "view_only",
        mutation_enabled: bool = True,
        governance_enabled: bool = True,
        allocations_frozen: bool = False,
    ):
        self.controls = SimpleNamespace(
            paused=paused,
            control_mode=control_mode,
            sandbox_only=False,
            allocations_frozen=allocations_frozen,
            defensive_mode=False,
            reduce_exposure_half=False,
            governance_enabled=governance_enabled,
            mutation_enabled=mutation_enabled,
            aggression_mode="balanced",
            full_system_enabled=False,
            force_send_mode="",
            force_gas_mode="",
        )
        self.audit = SimpleNamespace(tail=lambda limit=200: [])

    def set_controls(self, patch, actor="operator", reason=""):
        for k, v in patch.items():
            setattr(self.controls, k, v)
        return {"ok": True, "patch": patch, "reason": reason}


class _RT:
    def __init__(self, **kwargs):
        self._cc = _CC(**kwargs)
        self.calls = []

    def set_settings(self, **kwargs):
        self.calls.append(kwargs)


def test_command_center_requires_reason_for_posture_widening():
    rt = _RT(paused=True, control_mode="view_only")
    result = CommandCenterService().apply_controls(
        rt, {"patch": {"controlMode": "auto"}, "reason": ""}
    )
    assert result.ok is False
    assert result.error == "reason_required_for_posture_widening"
    assert result.payload["review_required"] is True


def test_command_center_blocks_governance_disable_without_pause():
    rt = _RT(paused=False, control_mode="assist")
    result = CommandCenterService().apply_controls(
        rt, {"patch": {"governanceEnabled": False}, "reason": "maintenance"}
    )
    assert result.ok is False
    assert result.error == "pause_required_before_governance_disable"


def test_command_center_blocks_auto_mode_while_allocations_frozen():
    rt = _RT(paused=True, control_mode="view_only", allocations_frozen=True)
    result = CommandCenterService().apply_controls(
        rt, {"patch": {"controlMode": "auto"}, "reason": "resume"}
    )
    assert result.ok is False
    assert result.error == "allocations_frozen"


class _CCInvalid(_CC):
    def set_controls(self, patch, actor="operator", reason=""):
        return {
            "ok": False,
            "status": "invalid",
            "reason_code": "invalid_control_patch",
            "error": "invalid_control_patch",
        }


class _RTInvalid(_RT):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._cc = _CCInvalid(**kwargs)


def test_command_center_surfaces_overlay_validation_failure_without_mutating_runtime():
    rt = _RTInvalid(paused=True, control_mode="view_only")
    result = CommandCenterService().apply_controls(
        rt, {"patch": {"sandboxOnly": "not-a-bool"}, "reason": "maintenance"}
    )
    assert result.ok is False
    assert result.error == "invalid_control_patch"
    assert rt.calls == []
    assert rt._cc.controls.sandbox_only is False




def test_command_center_accepts_top_level_control_fields_for_backward_compatible_operator_payloads():
    rt = _RT(paused=True, control_mode="view_only", mutation_enabled=True, governance_enabled=True)
    result = CommandCenterService().apply_controls(
        rt, {"controlMode": "assist", "reason": "resume in assist"}
    )
    assert result.ok is True
    assert result.payload["patch"]["control_mode"] == "assist"
    assert result.payload["reason"] == "resume in assist"
    assert rt._cc.controls.control_mode == "assist"
    assert rt._cc.controls.paused is False
    assert rt.calls == [{"auto_trading": True}]


def test_command_center_rejects_empty_control_payload_instead_of_silent_noop():
    rt = _RT(paused=True, control_mode="view_only")
    result = CommandCenterService().apply_controls(rt, {"reason": "no actual change"})
    assert result.ok is False
    assert result.error == "empty_control_patch"
    assert result.payload["status"] == "invalid"
    assert rt.calls == []


def test_command_center_rejects_ambiguous_nested_and_top_level_control_conflicts():
    rt = _RT(paused=True, control_mode="view_only")
    result = CommandCenterService().apply_controls(
        rt,
        {
            "patch": {"controlMode": "assist"},
            "controlMode": "auto",
            "reason": "ambiguous request",
        },
    )
    assert result.ok is False
    assert result.error == "ambiguous_control_patch"
    assert result.payload["status"] == "invalid"
    assert rt.calls == []
