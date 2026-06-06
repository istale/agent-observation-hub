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
    monkeypatch.setenv("AOH_PAYLOAD_MODE", "redacted")
    monkeypatch.setenv("AOH_OBSERVATION_DIR", str(tmp_path / "observation"))
    monkeypatch.setenv("AOH_OBSERVATION_TAIL_DISABLE", "1")

    from app.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def temp_data_dir(tmp_path, monkeypatch) -> Path:
    data = tmp_path / "data"
    monkeypatch.setenv("AOH_DATA_DIR", str(data))
    monkeypatch.setenv("AOH_DATABASE_PATH", str(data / "hub.sqlite3"))
    from app.config import get_settings

    get_settings.cache_clear()
    return data
