"""Every test gets a separate synthetic SQLite world; no legacy PostgreSQL imports."""

import os
from pathlib import Path
import sys
import tempfile
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_temp = tempfile.TemporaryDirectory(prefix="pixelledger-tests-")
os.environ["PIXELLEDGER_DB"] = str(Path(_temp.name) / "unused-default.db")
os.environ["PIXELLEDGER_API_KEY"] = ""


@pytest.fixture
def shop(tmp_path):
    from shop.database import Database
    from shop.engine import Shop

    world = Shop(Database(tmp_path / "shop.db"))
    world.initialize(42)
    return world


@pytest.fixture
def client(shop, monkeypatch):
    from fastapi.testclient import TestClient
    from shop import api

    monkeypatch.setattr(api, "shop", shop)
    monkeypatch.setattr(api, "API_KEY", "")
    with TestClient(api.app) as connection:
        yield connection


def pytest_sessionfinish(session, exitstatus):
    _temp.cleanup()
