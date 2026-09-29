from __future__ import annotations

import hashlib
import re

# Order matters: longer numeric patterns run first so a card number is not
# partially consumed by the CCCD or phone patterns.
PII_PATTERNS: dict[str, str] = {
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "credit_card": r"(?<!\d)\d{4}(?:[- ]?\d{4}){3}(?!\d)",
    "cccd": r"(?<!\d)\d{12}(?!\d)",
    "phone_vn": r"(?<!\d)(?:\+84|0)(?:[ .-]?\d){9}(?!\d)",
    # Vietnamese passport: one uppercase letter followed by 7 digits (e.g. C1234567).
    "passport": r"\b[A-Z]\d{7}\b",
}


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in PII_PATTERNS.items():
        safe = re.sub(pattern, f"[REDACTED_{name.upper()}]", safe)
    return safe


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
