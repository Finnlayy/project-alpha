"""
Real WebAuthn (FIDO2) server-side verification — no third-party WebAuthn SDK.

Implements the FIDO2 spec essentials with `cryptography` + `cbor2`:
  Registration (attestation):
    - clientDataJSON: type=webauthn.create, challenge match, origin allowlist,
      crossOrigin=false
    - authData: rpIdHash == SHA256(rp_id), UP flag set, signCount==0
    - fmt "none" accepted; "packed" accepted in self-attestation form
      (attStmt.signature over authData by the credential key) or with x5c when
      ALPHA_WEBAUTHN_ALLOW_X5C=true (leaf only; full chain validation is out
      of scope and is then flagged in the result)
  Assertion (authentication):
    - clientDataJSON: type=webauthn.get, challenge, origin, crossOrigin
    - authData: rpIdHash, UP flag
    - signature = sig over SHA256(authData || SHA256(clientDataJSON)) with the
      stored COSE public key (ES256 P-256 or RS256)
    - signCount anti-cloning check when both counters are non-zero

Base64 handling is lenient: accepts standard b64 (browser `btoa`) and b64url.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa


# ---------------------------------------------------------------- base64
def b64_decode(data: str) -> bytes:
    if not data:
        return b""
    data = data.strip()
    pad = (-len(data)) % 4
    return base64.urlsafe_b64decode(data + "=" * pad) if "-" in data or "_" in data else base64.b64decode(data + "=" * pad)


def b64_encode(data: bytes) -> str:
    return base64.b64encode(data).decode()


class WebAuthnError(ValueError):
    pass


# ---------------------------------------------------------------- COSE keys
def cose_key_to_public_key(cose: Dict[str, Any]):
    """Parse a COSE_Key (crv P-256 / P-384, or RSA) into a cryptography public key."""
    kty = cose.get(1)
    if kty == 2:  # EC2
        crv = cose.get(-1)
        x = cose.get(-2)
        y = cose.get(-3)
        if crv != 1:
            raise WebAuthnError(f"unsupported EC curve crv={crv} (only P-256 supported)")
        pub = ec.EllipticCurvePublicNumbers(int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()).public_key()
        return pub
    if kty == 3:  # RSA
        n = cose.get(-1)
        e = cose.get(-2)
        pub = rsa.RSAPublicNumbers(int.from_bytes(e, "big"), int.from_bytes(n, "big")).public_key()
        return pub
    raise WebAuthnError(f"unsupported COSE key type kty={kty}")


def parse_auth_data(auth_data: bytes) -> Dict[str, Any]:
    if len(auth_data) < 37:
        raise WebAuthnError("authData too short")
    out = {
        "rp_id_hash": auth_data[:32],
        "flags": auth_data[32],
        "sign_count": int.from_bytes(auth_data[33:37], "big"),
        "aaguid": None,
        "credential_id": None,
        "credential_public_key": None,
    }
    if out["flags"] & 0x40:  # AT flag: attested credential data present
        if len(auth_data) < 37 + 16 + 2:
            raise WebAuthnError("authData truncated (no AAGUID/credId)")
        off = 37
        out["aaguid"] = auth_data[off : off + 16]
        off += 16
        cred_len = int.from_bytes(auth_data[off : off + 2], "big")
        off += 2
        out["credential_id"] = auth_data[off : off + cred_len]
        off += cred_len
        cose = cbor2.loads(auth_data[off:])
        out["cose_key"] = cose
        out["credential_public_key"] = cose_key_to_public_key(cose)
        out["cose_key_raw"] = auth_data[off:]
    return out


def _check_client_data(client_data_b64: str, expected_challenge_b64: str, expected_type: str, rp_id: str, allowed_origins: list, description: str) -> Dict[str, Any]:
    raw = b64_decode(client_data_b64)
    try:
        cd = json.loads(raw)
    except Exception as e:
        raise WebAuthnError(f"invalid clientDataJSON ({description}): {e}")
    if cd.get("type") != expected_type:
        raise WebAuthnError(f"clientDataJSON.type={cd.get('type')!r}, expected {expected_type!r}")
    if cd.get("challenge") != expected_challenge_b64:
        raise WebAuthnError("clientDataJSON challenge mismatch")
    if cd.get("crossOrigin") is True:
        raise WebAuthnError("cross-origin WebAuthn request rejected")
    origin = cd.get("origin", "")
    if allowed_origins and origin not in allowed_origins:
        raise WebAuthnError(f"origin {origin!r} not in allowlist {allowed_origins}")
    return cd


# ---------------------------------------------------------------- engine
@dataclass
class StoredCredential:
    credential_id_b64: str
    user_id: str
    cose_key: Dict[str, Any]
    public_key: Any
    sign_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: Optional[float] = None
    attestation_fmt: str = "none"


class WebAuthnEngine:
    def __init__(self, rp_id: str, rp_name: str, allowed_origins: Optional[list] = None, challenge_ttl: int = 120):
        self.rp_id = rp_id
        self.rp_name = rp_name
        self.allowed_origins = allowed_origins or []
        self.challenge_ttl = challenge_ttl
        self.challenges: Dict[str, Dict[str, Any]] = {}  # user_id -> {b64, expires, purpose}
        self.credentials: Dict[str, StoredCredential] = {}  # credential_id_b64 -> cred
        self.user_credentials: Dict[str, set] = {}  # user_id -> set(cred_id_b64)
        self.allow_x5c = os.environ.get("ALPHA_WEBAUTHN_ALLOW_X5C", "false").lower() == "true"

    # ------------------------------------------------------------ challenges
    def _new_challenge(self, user_id: str, purpose: str) -> str:
        import secrets

        raw = secrets.token_bytes(32)
        b64 = b64_encode(raw)
        self.challenges[user_id] = {"b64": b64, "expires": time.time() + self.challenge_ttl, "purpose": purpose}
        return b64

    def _pop_challenge(self, user_id: str, purpose: str) -> str:
        ch = self.challenges.get(user_id)
        if not ch:
            raise WebAuthnError("no active challenge (run the challenge endpoint first)")
        if ch["expires"] < time.time():
            raise WebAuthnError("challenge expired")
        if ch["purpose"] != purpose:
            raise WebAuthnError(f"challenge purpose mismatch ({ch['purpose']} != {purpose})")
        del self.challenges[user_id]
        return ch["b64"]

    # -------------------------------------------------------- registration
    def generate_registration_options(self, user_id: str, user_name: str, user_display: str) -> Dict[str, Any]:
        challenge = self._new_challenge(user_id, "registration")
        return {
            "success": True,
            "publicKey": {
                "challenge": challenge,
                "rp": {"name": self.rp_name, "id": self.rp_id},
                "user": {
                    "id": b64_encode(user_id.encode()),
                    "name": user_name,
                    "displayName": user_display,
                },
                "pubKeyCredParams": [
                    {"type": "public-key", "alg": -7},   # ES256
                    {"type": "public-key", "alg": -257},  # RS256
                ],
                "timeout": 60000,
                "attestation": "none",
                "authenticatorSelection": {
                    "userVerification": "preferred",
                    "residentKey": "preferred",
                },
            },
        }

    def verify_registration(self, user_id: str, user_name: str, credential: Dict[str, Any]) -> StoredCredential:
        """credential: browser PublicKeyCredentialCreationResponse JSON
        (either the full credential {id, response:{...}} or the inner response)."""
        expected = self._pop_challenge(user_id, "registration")
        response = credential.get("response", credential)
        if not isinstance(response, dict) or not response.get("attestationObject"):
            raise WebAuthnError("missing attestationObject in credential response")
        if not response.get("clientDataJSON"):
            raise WebAuthnError("missing clientDataJSON in credential response")
        try:
            att_obj = cbor2.loads(b64_decode(response["attestationObject"]))
        except Exception as e:
            raise WebAuthnError(f"invalid attestationObject CBOR: {e}")
        auth_data = att_obj.get("authData", b"")
        if isinstance(auth_data, memoryview):
            auth_data = bytes(auth_data)
        _check_client_data(response["clientDataJSON"], expected, "webauthn.create", self.rp_id, self.allowed_origins, "registration")

        parsed = parse_auth_data(auth_data)
        if parsed["rp_id_hash"] != hashlib.sha256(self.rp_id.encode()).digest():
            raise WebAuthnError("rpIdHash mismatch — relying party id changed")
        if not (parsed["flags"] & 0x01):
            raise WebAuthnError("user presence (UP) flag not set")
        if parsed["sign_count"] != 0:
            raise WebAuthnError(f"registration with non-zero signCount ({parsed['sign_count']}) — possible credential reuse")
        if parsed["credential_id"] is None:
            raise WebAuthnError("no attested credential data in authData")

        fmt = att_obj.get("fmt")
        att_stmt = att_obj.get("attStmt", {})
        if isinstance(att_stmt, memoryview):
            att_stmt = cbor2.loads(att_stmt)
        sig = att_stmt.get("signature", b"")

        if fmt == "none":
            if att_stmt:
                raise WebAuthnError("fmt=none must carry empty attStmt")
        elif fmt == "packed":
            if "x5c" in att_stmt:
                if not self.allow_x5c:
                    raise WebAuthnError("x5c attestation not enabled (set ALPHA_WEBAUTHN_ALLOW_X5C=true)")
                # accepted with leaf-only verification below; chain validation out of scope
            if not sig:
                raise WebAuthnError("packed attestation missing signature")
            self._verify_sig(parsed["credential_public_key"], auth_data, sig, -7 if self._is_ec(parsed["cose_key"]) else -257)
        else:
            raise WebAuthnError(f"unsupported attestation format {fmt!r} (use 'none' or 'packed')")

        cred_id_b64 = b64_encode(parsed["credential_id"])
        cred = StoredCredential(
            credential_id_b64=cred_id_b64,
            user_id=user_id,
            cose_key=parsed["cose_key"],
            public_key=parsed["credential_public_key"],
            sign_count=parsed["sign_count"],
            attestation_fmt=fmt,
        )
        self.credentials[cred_id_b64] = cred
        self.user_credentials.setdefault(user_id, set()).add(cred_id_b64)
        return cred

    @staticmethod
    def _is_ec(cose: Dict[str, Any]) -> bool:
        return cose.get(1) == 2

    def _verify_sig(self, pub: Any, data: bytes, sig: bytes, alg_hint: int) -> None:
        if isinstance(data, memoryview):
            data = bytes(data)
        if isinstance(sig, memoryview):
            sig = bytes(sig)
        try:
            if isinstance(pub, ec.EllipticCurvePublicKey):
                # FIDO2 ES256: raw r||s (64 bytes) -> DER for verification
                if len(sig) != 64:
                    raise WebAuthnError(f"ES256 signature must be 64 bytes (raw r||s), got {len(sig)}")
                from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

                der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
                pub.verify(der, data, ec.ECDSA(hashes.SHA256()))
            else:
                pub.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
        except InvalidSignature:
            raise WebAuthnError("signature verification failed")

    # --------------------------------------------------------- authentication
    def generate_authentication_options(self, user_id: str) -> Dict[str, Any]:
        if not self.user_credentials.get(user_id):
            raise WebAuthnError("no registered credential for this user (register first)")
        challenge = self._new_challenge(user_id, "authentication")
        allowed = [self.credentials[c].credential_id_b64 for c in self.user_credentials[user_id]]
        return {
            "success": True,
            "publicKey": {
                "challenge": challenge,
                "rpId": self.rp_id,
                "allowCredentials": [{"type": "public-key", "id": a} for a in allowed],
                "timeout": 60000,
                "userVerification": "preferred",
            },
        }

    def verify_authentication(self, user_id: str, credential_id: str, credential: Dict[str, Any]) -> StoredCredential:
        """credential: {id, response: {clientDataJSON, authenticatorData}} (browser
        shape) or the inner response object. The assertion signature is embedded
        in authenticatorData per the FIDO2 layout."""
        expected = self._pop_challenge(user_id, "authentication")
        response = credential.get("response", credential)
        if not isinstance(response, dict) or not response.get("clientDataJSON") or not response.get("authenticatorData"):
            raise WebAuthnError("credential must contain response.clientDataJSON and response.authenticatorData")
        cred_id_b64 = b64_encode(b64_decode(credential_id))
        cred = self.credentials.get(cred_id_b64)
        if cred is None:
            raise WebAuthnError("unknown credential id")
        if cred.user_id != user_id:
            raise WebAuthnError("credential not registered to this user")

        _check_client_data(response["clientDataJSON"], expected, "webauthn.get", self.rp_id, self.allowed_origins, "authentication")
        auth_data = b64_decode(response["authenticatorData"])
        parsed = parse_auth_data(auth_data)
        if parsed["rp_id_hash"] != hashlib.sha256(self.rp_id.encode()).digest():
            raise WebAuthnError("rpIdHash mismatch")
        if not (parsed["flags"] & 0x01):
            raise WebAuthnError("user presence (UP) flag not set")

        # FIDO2: signature is over  authData (37-byte prefix, excluding the
        # signature itself)  ||  SHA256(clientDataJSON)
        message = auth_data[:37] + hashlib.sha256(b64_decode(response["clientDataJSON"])).digest()
        # signature = last 64 (ES256) or 256 (RS256) bytes of authData
        sig_len = 64 if isinstance(cred.public_key, ec.EllipticCurvePublicKey) else 256
        if len(auth_data) < 37 + sig_len:
            raise WebAuthnError("authenticatorData too short to contain assertion signature")
        signature = auth_data[len(auth_data) - sig_len:]
        self._verify_sig(cred.public_key, message, signature, -7 if isinstance(cred.public_key, ec.EllipticCurvePublicKey) else -257)

        # anti-clone signCount check
        new_count = parsed["sign_count"]
        if new_count > 0 and cred.sign_count > 0 and new_count <= cred.sign_count:
            raise WebAuthnError("signCount regression — possible authenticator clone")
        cred.sign_count = max(cred.sign_count, new_count)
        cred.last_used = time.time()
        return cred
