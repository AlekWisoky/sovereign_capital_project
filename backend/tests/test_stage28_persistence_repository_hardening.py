from __future__ import annotations

import json
from pathlib import Path

from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.edge_model_repository import EdgeModelRepository
from victor_ai_bot.persistence.repositories.launch_repository import LaunchRepository


def _db(tmp_path: Path) -> PersistenceDB:
    return PersistenceDB(str(tmp_path / "state.sqlite3"))


def test_launch_repository_load_falls_back_to_db_on_invalid_file(tmp_path: Path) -> None:
    db = _db(tmp_path)
    repo = LaunchRepository(db, chain="base", path=str(tmp_path / "launch.json"))
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO launch_state(chain,payload_json,updated_ts_ms) VALUES(?,?,?)",
            ("base", json.dumps({"ok": True, "updated_ts_ms": 7}), 7),
        )
    (tmp_path / "launch.json").write_text("{bad-json", encoding="utf-8")

    payload = repo.load()

    assert payload == {"ok": True, "updated_ts_ms": 7}


def test_launch_repository_load_returns_empty_for_non_mapping_db_payload(tmp_path: Path) -> None:
    db = _db(tmp_path)
    repo = LaunchRepository(db, chain="base", path=str(tmp_path / "launch.json"))
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO launch_state(chain,payload_json,updated_ts_ms) VALUES(?,?,?)",
            ("base", json.dumps([1, 2, 3]), 0),
        )

    assert repo.load() == {}


def test_edge_model_repository_skips_invalid_prior_rows(tmp_path: Path) -> None:
    db = _db(tmp_path)
    repo = EdgeModelRepository(db, chain="base")
    repo.upsert_prior(
        key="good",
        family="flash_arb",
        route_family="rf",
        venue="uni",
        lane="public",
        regime="normal",
        payload={"count": 3, "updated_ts_ms": 11},
    )
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO edge_model_priors(chain,key,family,route_family,venue,lane,regime,count,success_ewma,competition_ewma,quality_ewma,freshness_ewma,slippage_bias_ewma,failure_risk_ewma,updated_ts_ms,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "base",
                "bad",
                "flash_arb",
                "rf",
                "uni",
                "public",
                "normal",
                0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0,
                "{bad-json",
            ),
        )

    rows = repo.list_priors(family="flash_arb")

    assert rows == [{"count": 3, "updated_ts_ms": 11}]


def test_edge_model_repository_get_prior_returns_empty_for_non_mapping_payload(tmp_path: Path) -> None:
    db = _db(tmp_path)
    repo = EdgeModelRepository(db, chain="base")
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO edge_model_priors(chain,key,family,route_family,venue,lane,regime,count,success_ewma,competition_ewma,quality_ewma,freshness_ewma,slippage_bias_ewma,failure_risk_ewma,updated_ts_ms,payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "base",
                "k1",
                "flash_arb",
                "rf",
                "uni",
                "public",
                "normal",
                0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0,
                json.dumps([1, 2, 3]),
            ),
        )

    assert repo.get_prior(key="k1") == {}
