"""Do not forward application secrets or personal identifiers into research."""
import re
from app.core.exceptions import ApiError

SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{12,}|(?:api[_ -]?key|password)\s*[:=]\s*\S+|[a-z]+(?:\+[a-z]+)?://[^\s/@]+:[^\s/@]+@", re.I)
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")


def safe_text(text, secrets=()):
    text = str(text)
    for value in secrets:
        if value and len(value) >= 6:
            text = text.replace(value, "[redacted]")
    return EMAIL_PATTERN.sub("[contact redacted]", SECRET_PATTERN.sub("[secret redacted]", text))


def sanitize(value, secrets=()):
    if isinstance(value, str):
        return safe_text(value, secrets)
    if isinstance(value, list):
        return [sanitize(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: sanitize(item, secrets) for key, item in value.items()}
    return value


def check_question(text, secrets=()):
    if not text.strip():
        raise ApiError("invalid_ai_question", "Enter a company research question.", 422)
    if SECRET_PATTERN.search(text) or any(value and len(value) >= 6 and value in text for value in secrets):
        raise ApiError("sensitive_ai_input", "Remove credentials from the research question or conversation.", 422)
