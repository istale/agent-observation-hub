from pathlib import Path


def test_project_does_not_depend_on_litellm_package():
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").lower()

    assert '"litellm' not in pyproject
    assert "'litellm" not in pyproject


def test_application_code_does_not_import_litellm():
    app_files = list(Path("app").rglob("*.py"))

    offenders = []
    for path in app_files:
        text = path.read_text(encoding="utf-8").lower()
        if "import litellm" in text or "from litellm" in text:
            offenders.append(str(path))

    assert offenders == []


def test_default_upstream_is_not_litellm_local_port():
    config = Path("app/config.py").read_text(encoding="utf-8")
    configure_section = (
        Path("README.md")
        .read_text(encoding="utf-8")
        .split("## Configure", maxsplit=1)[1]
        .split("Point OpenClaw", maxsplit=1)[0]
    )

    assert "localhost:4000" not in config
    assert "127.0.0.1:4000" not in configure_section
