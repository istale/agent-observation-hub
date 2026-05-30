import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("AOH_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AOH_DATABASE_PATH", str(tmp_path / "data" / "hub.sqlite3"))
    monkeypatch.setenv("UPSTREAM_OPENAI_BASE_URL", "http://upstream.test")
    monkeypatch.setenv("ALLOW_RAW_VIEW", "false")

    from app.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def temp_data_dir(tmp_path, monkeypatch) -> Path:
    data = tmp_path / "data"
    monkeypatch.setenv("AOH_DATA_DIR", str(data))
    monkeypatch.setenv("AOH_DATABASE_PATH", str(data / "hub.sqlite3"))
    return data
