from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
RENDER_YAML = ROOT / "render.yaml"


def _service() -> dict:
    raw = yaml.safe_load(RENDER_YAML.read_text(encoding="utf-8"))
    services = raw.get("services") or []
    assert services
    return dict(services[0])


def test_render_uses_production_docker_entrypoint_and_persistent_runtime_data():
    service = _service()
    assert service["type"] == "web"
    assert service["runtime"] == "docker"
    assert service["dockerfilePath"] == "./Dockerfile"
    assert service["dockerContext"] == "."
    assert service["healthCheckPath"] == "/health"
    assert service["autoDeploy"] is True
    assert service["disk"]["mountPath"] == "/app/backend/data"


def test_render_enables_omar_without_authorizing_public_broadcast():
    env = {item["key"]: item for item in _service()["envVars"]}
    assert env["VICTOR_ENABLE_OMAR"]["value"] == "1"
    assert env["VICTOR_AUTOSTART"]["value"] == "1"
    assert env["VICTOR_PUBLIC_ALLOW_BROADCAST"]["value"] == "0"
    assert env["VICTOR_DEPLOYMENT_MODE"]["value"] == "public"
    assert env["VICTOR_CONFIG"]["value"] == "/app/backend/config/ethereum.yaml"
    assert env["VICTOR_ADMIN_KEY"]["sync"] is False


def test_render_config_path_exists_in_production_image_source_tree():
    config_path = ROOT / "backend" / "config" / "ethereum.yaml"
    assert config_path.is_file()
