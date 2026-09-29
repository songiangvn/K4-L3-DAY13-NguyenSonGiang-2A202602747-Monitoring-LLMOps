from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    out = scrub_text("CCCD cua toi la 001203004567")
    assert "001203004567" not in out
    assert "REDACTED_CCCD" in out


def test_scrub_credit_card_formats() -> None:
    for card in ("4111 1111 1111 1111", "4111-1111-1111-1111", "4111111111111111"):
        out = scrub_text(f"card {card} please")
        assert card not in out
        assert "REDACTED_CREDIT_CARD" in out
        assert "REDACTED_CCCD" not in out
        assert "REDACTED_PHONE_VN" not in out


def test_scrub_passport() -> None:
    out = scrub_text("Passport C1234567")
    assert "C1234567" not in out
    assert "REDACTED_PASSPORT" in out


def test_scrub_keeps_safe_text() -> None:
    text = "How do I debug tail latency at P95 for 3 minutes?"
    assert scrub_text(text) == text


def test_scrub_event_redacts_nested_fields() -> None:
    from app.logging_config import scrub_event

    event = {
        "event": "request_failed",
        "correlation_id": "req-1a2b3c4d",
        "payload": {"detail": "bad input student@vinuni.edu.vn", "extra": ["0987654321"]},
    }
    out = scrub_event(None, "info", event)
    assert out["correlation_id"] == "req-1a2b3c4d"
    assert "student@" not in out["payload"]["detail"]
    assert "0987654321" not in out["payload"]["extra"][0]
