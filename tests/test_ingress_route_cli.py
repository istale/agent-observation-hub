import subprocess


def test_add_ingress_route_cli_creates_route(temp_data_dir):
    db_path = temp_data_dir / "hub.sqlite3"

    result = subprocess.run(
        [
            ".venv312/bin/python",
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
    )

    assert result.returncode == 0
    assert "43180" in result.stdout
    assert "hermes" in result.stdout
