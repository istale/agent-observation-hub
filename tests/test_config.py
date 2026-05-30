from app.config import Settings


def test_payload_mode_defaults_to_raw(monkeypatch):
    monkeypatch.delenv("AOH_PAYLOAD_MODE", raising=False)

    settings = Settings()

    assert settings.payload_mode == "raw"


def test_payload_mode_invalid_value_falls_back_to_redacted(monkeypatch):
    monkeypatch.setenv("AOH_PAYLOAD_MODE", "invalid")

    settings = Settings()

    assert settings.payload_mode == "redacted"
