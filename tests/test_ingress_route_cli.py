import os
import subprocess
import sys
from pathlib import Path


def test_add_ingress_route_cli_creates_route(temp_data_dir):
    db_path = temp_data_dir / "hub.sqlite3"

    # The CLI imports ``app.storage.repositories`` from the hub root, so the
    # subprocess needs that root on its PYTHONPATH. We resolve it from this
    # test file rather than from the test runner's cwd so the test passes
    # whether invoked from inside the hub dir or from the workspace root.
    hub_root = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    env["PYTHONPATH"] = str(hub_root) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/add_ingress_route.py",
            "--db",
            str(db_path),
            "--host",
            "127.0.0.1",
            "--port",
            "43180",
            "--path-prefix",
            "/v1",
            "--tenant-id",
            "local",
            "--user-hash",
            "istale",
            "--agent-id",
            "hermes",
            "--channel",
            "discord",
            "--note",
            "main Hermes gateway",
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=hub_root,
        env=env,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "43180" in result.stdout
    assert "hermes" in result.stdout
