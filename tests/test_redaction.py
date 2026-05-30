from app.trace.redaction import redact


def test_redaction_masks_nested_tokens_email_passwords_and_authorization():
    payload = {
        "headers": {"authorization": "Bearer sk-live-secret"},
        "email": "person@example.com",
        "password": "hunter2",
        "nested": ["token=abc123", {"api_key": "sk-test-value"}],
        "ssh": "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----",
    }

    redacted = redact(payload)
    rendered = str(redacted)

    assert "person@example.com" not in rendered
    assert "hunter2" not in rendered
    assert "sk-live-secret" not in rendered
    assert "sk-test-value" not in rendered
    assert "OPENSSH PRIVATE KEY" not in rendered
    assert "[REDACTED]" in rendered
