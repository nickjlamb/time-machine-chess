"""Games-played counter tests (uses a temp DATA_DIR via env)."""
import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import backend.app
    importlib.reload(backend.app)
    yield TestClient(backend.app.app)
    monkeypatch.delenv("DATA_DIR")
    importlib.reload(backend.app)


def test_counter_increments(client):
    assert client.get("/api/stats").json()["games_total"] == 0
    for _ in range(3):
        assert client.post("/api/event/game-start", json={"era": "romantic"}).status_code == 204
    client.post("/api/event/game-start", json={"era": "soviet"})
    s = client.get("/api/stats").json()
    assert s["games_total"] == 4
    assert s["per_era"] == {"romantic": 3, "soviet": 1}


def test_unknown_era_not_counted(client):
    client.post("/api/event/game-start", json={"era": "jazz"})
    assert client.get("/api/stats").json()["games_total"] == 0
