"""Functional tests for pinned constraints API + snapshot file."""
from __future__ import annotations

import json
from pathlib import Path

from app.config import get_settings


def test_post_creates_and_snapshots(app_client):
    resp = app_client.post("/api/constraints", json={"text": "prefer grep over vector RAG"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"].startswith("c_")

    listed = app_client.get("/api/constraints").json()["constraints"]
    assert len(listed) == 1
    assert listed[0]["text"] == "prefer grep over vector RAG"

    snap = json.loads((get_settings().observation_dir / "constraints.json").read_text())
    assert snap["constraints"][0]["text"] == "prefer grep over vector RAG"
    assert "updated_at" in snap


def test_empty_text_rejected(app_client):
    resp = app_client.post("/api/constraints", json={"text": "   "})
    assert resp.status_code == 400


def test_delete_removes_and_resnapshots(app_client):
    cid = app_client.post("/api/constraints", json={"text": "first"}).json()["id"]
    app_client.post("/api/constraints", json={"text": "second"})

    resp = app_client.delete(f"/api/constraints/{cid}")
    assert resp.status_code == 200

    remaining = app_client.get("/api/constraints").json()["constraints"]
    assert len(remaining) == 1
    assert remaining[0]["text"] == "second"

    snap = json.loads((get_settings().observation_dir / "constraints.json").read_text())
    assert len(snap["constraints"]) == 1
    assert snap["constraints"][0]["text"] == "second"


def test_delete_missing_returns_404(app_client):
    resp = app_client.delete("/api/constraints/does_not_exist")
    assert resp.status_code == 404


def test_scope_filter(app_client):
    app_client.post("/api/constraints", json={"text": "global rule"})
    app_client.post("/api/constraints", json={"text": "project rule", "scope": "proj-x"})

    all_ = app_client.get("/api/constraints").json()["constraints"]
    assert len(all_) == 2

    only_proj = app_client.get("/api/constraints?scope=proj-x").json()["constraints"]
    assert len(only_proj) == 1
    assert only_proj[0]["text"] == "project rule"
