from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request

from .config import settings

_HONEYPOT_NAMES = {"company_url", "website"}
_MIN_FILL_SECONDS = 3
_MAX_FORM_AGE_SECONDS = 2 * 60 * 60
_RATE_LIMIT_COUNT = 3
_RATE_LIMIT_WINDOW = 60 * 60
_URL_RE = re.compile(r"https?://|www\.", re.I)

_lock = Lock()
_ip_hits: dict[str, deque[float]] = defaultdict(deque)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:80]
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def make_form_token(now: int | None = None) -> str:
    ts = str(int(now if now is not None else time.time()))
    sig = hmac.new(settings.secret_key.encode(), ts.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{ts}.{sig}"


def verify_form_token(token: str) -> bool:
    if not token or "." not in token:
        return False
    ts, sig = token.split(".", 1)
    if not ts.isdigit():
        return False
    expected = hmac.new(settings.secret_key.encode(), ts.encode(), hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(sig, expected):
        return False
    age = time.time() - int(ts)
    return _MIN_FILL_SECONDS <= age <= _MAX_FORM_AGE_SECONDS


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    with _lock:
        hits = _ip_hits[ip]
        while hits and now - hits[0] > _RATE_LIMIT_WINDOW:
            hits.popleft()
        if len(hits) >= _RATE_LIMIT_COUNT:
            return True
        hits.append(now)
        return False


def looks_like_spam(name: str, message: str, email: str = "") -> bool:
    blob = f"{name}\n{message}\n{email}".lower()
    if _URL_RE.search(message or "") and len(_URL_RE.findall(message or "")) >= 2:
        return True
    spam_markers = (
        "crypto",
        "casino",
        "viagra",
        "cialis",
        "seo service",
        "backlink",
        "guest post",
        "binance",
        "nft ",
    )
    if any(marker in blob for marker in spam_markers):
        return True
    if len(re.findall(r"[A-Za-z]{20,}", message or "")) >= 3 and not re.search(r"[А-Яа-яЁё]", message or ""):
        return True
    return False


def reject_contact_spam(
    request: Request,
    *,
    honeypot: str,
    form_token: str,
    name: str,
    email: str,
    message: str,
) -> str | None:
    """Return a reason code if spam, else None. Rate-limit records only for real attempts."""
    if (honeypot or "").strip():
        return "honeypot"
    if not verify_form_token(form_token):
        return "token"
    if looks_like_spam(name, message, email):
        return "content"
    ip = client_ip(request)
    if is_rate_limited(ip):
        return "rate"
    return None


def spam_http_error(reason: str) -> HTTPException:
    if reason == "rate":
        return HTTPException(429, "Слишком много заявок. Попробуйте позже.")
    if reason == "token":
        return HTTPException(400, "Форма устарела. Обновите страницу и отправьте ещё раз.")
    return HTTPException(400, "Не удалось отправить заявку.")
