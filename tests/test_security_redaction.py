from app.trace.redaction import redact


def test_redaction_masks_cookie_headers():
    payload = {
        "headers": {
            "cookie": "sessionid=secret",
            "set-cookie": "refresh=secret; HttpOnly",
        }
    }

    rendered = str(redact(payload))

    assert "sessionid=secret" not in rendered
    assert "refresh=secret" not in rendered
    assert "[REDACTED]" in rendered

