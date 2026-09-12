"""
Signed operator session tokens.

Format:  base64url(payload_json) . base64url(HMAC-SHA256(payload_b64, secret))
Payload: {sub, roles, exp, iat, jti}
The HMAC secret is generated once and persisted (0600) so tokens survive
restarts. Revocation is an in-memory jti set (single-node deployment).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from typing import Any, Dict, Optional


class SessionService:
    def __init__(self, secret: "bytes | str", ttl_seconds: int = 86400):
        self.secret = secret.encode("utf-8") if isinstance(secret, str) else secret
        self.ttl = ttl_seconds
        self._revoked: set = set()
        self._lock = threading.Lock()

    @staticmethod
    def _b64u(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    @staticmethod
    def _ub64(s: str) -> bytes:
        return base64.urlsafe_b64decode(s + "=" * ((-len(s)) % 4))

    def mint(self, subject: str, roles: Optional[list] = None) -> str:
        payload = {
            "sub": subject,
            "roles": roles or ["OPERATOR"],
            "exp": int(time.time()) + self.ttl,
            "iat": int(time.time()),
            "jti": secrets.token_hex(12),
        }
        payload_b64 = self._b64u(json.dumps(payload, separators=(",", ":")).encode())
        sig = self._b64u(hmac.new(self.secret, payload_b64.encode(), hashlib.sha256).digest())
        return f"{payload_b64}.{sig}"

    def verify(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        if not token or "." not in token:
            return None
        payload_b64, _, sig = token.partition(".")
        expected = self._b64u(hmac.new(self.secret, payload_b64.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        try:
            payload = json.loads(self._ub64(payload_b64))
        except Exception:
            return None
        if payload.get("exp", 0) < time.time():
            return None
        with self._lock:
            if payload.get("jti") in self._revoked:
                return None
        return payload

    def revoke(self, token: str) -> bool:
        payload = self.verify(token)
        if not payload:
            return False
        with self._lock:
            self._revoked.add(payload["jti"])
        return True
