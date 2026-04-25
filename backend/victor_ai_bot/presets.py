from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Any, Tuple
import yaml
from .jsonsafe import to_json_safe


def _config_root() -> Path:
    return (Path(__file__).resolve().parent.parent / "config").resolve()


def find_preset_path(chain: str, name: str) -> Path:
    chain = (chain or "").lower().strip()
    name = (name or "").lower().strip()
    root = _config_root()

    # Primary: config/<chain>.yaml as default preset
    if name in ("default", ""):
        p = root / f"{chain}.yaml"
        if p.exists():
            return p

    # Secondary: config/presets/<chain>/<name>.yaml
    p2 = root / "presets" / chain / f"{name}.yaml"
    if p2.exists():
        return p2

    # Fallback: treat <name> as filename stem in config root
    p3 = root / f"{name}.yaml"
    if p3.exists():
        return p3

    raise FileNotFoundError(f"preset not found: {chain}/{name}")


def list_presets() -> Dict[str, List[str]]:
    root = _config_root()
    out: Dict[str, List[str]] = {}

    # default chain yaml files
    for p in root.glob("*.yaml"):
        chain = p.stem.lower()
        out.setdefault(chain, [])
        if "default" not in out[chain]:
            out[chain].append("default")

    # optional extra presets
    preset_root = root / "presets"
    if preset_root.exists():
        for chain_dir in preset_root.iterdir():
            if not chain_dir.is_dir():
                continue
            chain = chain_dir.name.lower()
            out.setdefault(chain, [])
            for f in chain_dir.glob("*.yaml"):
                nm = f.stem.lower()
                if nm not in out[chain]:
                    out[chain].append(nm)

    # stable order
    for k in list(out.keys()):
        out[k] = sorted(out[k])
    return dict(sorted(out.items()))


def get_preset(chain: str, name: str) -> Dict[str, Any]:
    p = find_preset_path(chain, name)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    raw["__preset__"] = {"chain": chain, "name": name, "path": str(p)}
    return to_json_safe(raw)
