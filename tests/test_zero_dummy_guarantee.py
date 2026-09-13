"""
INVARIANT 1 — ZERO-DUMMY GUARANTEE regression tests.

These lock down the purge of fabricated state. Before this suite existed the
codebase invented data in three places whenever credentials were missing:

  * ``SettingsEnvManager.get_credentials_status()`` returned the placeholder key
    previews ``"9sPO••••vjo8Z (sim)"`` / ``"7EG7••••JToFpf+ (sim)"`` and
    ``source="simulated"`` — a Kraken API key that does not exist, rendered in
    the dashboard.
  * ``KrakenDualAuthModal.tsx`` / ``KrakenLedgersPanel.tsx`` fell back to those
    same literals client-side and showed a ``Simuliert`` / ``Simulierter Modus``
    badge for a mode that has never existed.
  * ``TelegramBotEngine._send_telegram_request()`` returned
    ``{"ok": True, "simulated": True}`` without a token, i.e. it reported a
    successful delivery that never happened.

The required behaviour is an explicit, type-safe degraded state
(``not_configured`` / ``offline`` + ``UNCONFIGURED_CREDENTIALS``), never a
synthetic value. A final source-level scan makes reintroduction impossible.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import KrakenCredentials, Settings
from app.security.SettingsEnvManager import SettingsEnvManager
from app.telegram.TelegramBotEngine import TelegramBotEngine

REPO_ROOT = Path(__file__).resolve().parents[1]

SPOT_VARS = ("KRAKEN_SPOT_API_KEY", "KRAKEN_SPOT_PRIVATE_KEY", "KRAKEN_API_KEY", "KRAKEN_PRIVATE_KEY")
FUTURES_VARS = (
    "KRAKEN_FUTURES_API_KEY",
    "KRAKEN_FUTURES_PRIVATE_KEY",
    "KRAKEN_PRO_API_KEY",
    "KRAKEN_PRO_PRIVATE_KEY",
)

# Literals that must never appear in backend or UI source again.
BANNED_LITERALS = (
    "9sPO",
    "7EG7",
    "(sim)",
    "Simulierter Modus",
    "'simulated'",
    '"simulated"',
    '"ok": True, "simulated"',
)


@pytest.fixture
def no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guarantee an unconfigured environment regardless of the host's .env."""
    for var in SPOT_VARS + FUTURES_VARS + ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        monkeypatch.delenv(var, raising=False)


# ------------------------------------------------------- SettingsEnvManager
def test_credentials_status_never_fabricates_a_key_preview(no_credentials: None) -> None:
    status = SettingsEnvManager().get_credentials_status()

    assert status["hasSpotCredentials"] is False
    assert status["hasFuturesCredentials"] is False
    assert status["anyConfigured"] is False
    assert status["bothConfigured"] is False

    for venue in ("spot", "futures"):
        block = status[venue]
        assert block["configured"] is False
        assert block["keyPreview"] == "", f"{venue} invented a key preview: {block['keyPreview']!r}"
        assert block["source"] == "not_configured", block["source"]

    serialized = json.dumps(status, ensure_ascii=False)
    for banned in BANNED_LITERALS:
        assert banned not in serialized, f"fabricated credential state leaked: {banned!r}"


def test_credentials_status_masks_real_keys_and_never_leaks_the_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_key = "abcdef1234567890WXYZ"
    secret = "kQH5HW/8p1uGOVjbgWA7FunAmGO8lsSUXNsu3eow76sz84Q18fWxnyRzBHCd3pd5nE9qa99HAZtuZuj6F1huXg=="
    for var in FUTURES_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", api_key)
    monkeypatch.setenv("KRAKEN_SPOT_PRIVATE_KEY", secret)

    status = SettingsEnvManager().get_credentials_status()
    spot = status["spot"]

    assert status["hasSpotCredentials"] is True
    assert spot["configured"] is True
    assert spot["source"] == "env"
    # masked: shows a prefix/suffix only, never the whole key
    assert spot["keyPreview"] != api_key
    assert "\u2022\u2022\u2022\u2022" in spot["keyPreview"]
    assert spot["keyPreview"].startswith(api_key[:4])

    serialized = json.dumps(status, ensure_ascii=False)
    assert api_key not in serialized, "full API key must never leave the backend"
    assert secret not in serialized, "private key must never leave the backend"
    # futures is still unconfigured and must stay honest
    assert status["futures"]["keyPreview"] == ""
    assert status["futures"]["source"] == "not_configured"


def test_mask_key_returns_none_for_absent_key() -> None:
    mgr = SettingsEnvManager()
    assert mgr.mask_key(None) is None
    assert mgr.mask_key("") is None
    assert mgr.mask_key("   ") is None


# ------------------------------------------------------------------- config
def test_config_key_preview_is_empty_when_unconfigured(no_credentials: None) -> None:
    creds = KrakenCredentials()
    assert creds.configured is False
    assert creds.key_preview == ""


def test_api_credentials_status_uses_not_configured(no_credentials: None) -> None:
    """The payload the UI actually renders (routes._credentials_status)."""
    from app.api.routes import _credentials_status

    app_stub = SimpleNamespace(settings=Settings())
    status = _credentials_status(app_stub)  # type: ignore[arg-type]

    assert status["hasCredentials"] is False
    for venue in ("spot", "futures"):
        assert status[venue]["configured"] is False
        assert status[venue]["keyPreview"] == ""
        assert status[venue]["source"] == "not_configured"

    serialized = json.dumps(status, ensure_ascii=False)
    for banned in BANNED_LITERALS:
        assert banned not in serialized, f"fabricated credential state leaked: {banned!r}"


# ----------------------------------------------------------------- telegram
def test_telegram_without_token_is_offline_never_simulated(no_credentials: None) -> None:
    bot = TelegramBotEngine(bot_token=None, default_chat_id="12345")
    assert bot.is_configured() is False

    result = bot._send_telegram_request("sendMessage", {"chat_id": "12345", "text": "hi"})

    assert result["ok"] is False, "an undelivered message must not report success"
    assert result["status"] == "offline"
    assert result["reason"] == "UNCONFIGURED_CREDENTIALS"
    assert result["method"] == "sendMessage"
    assert "simulated" not in result, "no simulated-delivery flag may be returned"
    assert "result" not in result, "must not echo the payload as if it were sent"


def test_telegram_send_message_fails_closed_without_token(no_credentials: None) -> None:
    bot = TelegramBotEngine(bot_token=None, default_chat_id="12345")
    result = bot.send_message("M8 quarantine alert")

    assert result["ok"] is False
    assert result.get("reason") == "UNCONFIGURED_CREDENTIALS"
    assert result.get("status") == "offline"


def test_telegram_send_message_requires_a_chat_id(no_credentials: None) -> None:
    bot = TelegramBotEngine(bot_token="123456:ABC-real-token-shape", default_chat_id=None)
    result = bot.send_message("no destination")

    assert result["ok"] is False
    assert "chat_id" in str(result.get("error", "")).lower()


def test_telegram_is_configured_requires_both_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    assert TelegramBotEngine().is_configured() is False
    assert TelegramBotEngine(bot_token="t").is_configured() is False
    assert TelegramBotEngine(default_chat_id="c").is_configured() is False
    assert TelegramBotEngine(bot_token="t", default_chat_id="c").is_configured() is True


# ------------------------------------------------------ source-level guard
def _source_files() -> list[Path]:
    files = [p for p in (REPO_ROOT / "app").rglob("*.py")]
    files += [p for p in (REPO_ROOT / "src").rglob("*.ts")]
    files += [p for p in (REPO_ROOT / "src").rglob("*.tsx")]
    return [p for p in files if "__pycache__" not in p.parts]


def test_no_fabricated_credential_placeholders_in_source() -> None:
    """Scan backend and UI source for the banned dummy literals."""
    files = _source_files()
    assert files, "no source files discovered — the scan would be vacuous"

    offenders: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for banned in BANNED_LITERALS:
            if banned in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {banned}")

    assert not offenders, "fabricated credential/state literals found:\n" + "\n".join(offenders)


def test_env_example_exists_and_carries_no_secret_values() -> None:
    """`.env.example` is referenced by README, bin/run.sh and SettingsEnvManager."""
    example = REPO_ROOT / ".env.example"
    assert example.is_file(), ".env.example is missing (documented by README/run.sh)"

    text = example.read_text(encoding="utf-8")
    for var in (
        "KRAKEN_SPOT_API_KEY",
        "KRAKEN_SPOT_PRIVATE_KEY",
        "KRAKEN_FUTURES_API_KEY",
        "KRAKEN_FUTURES_PRIVATE_KEY",
        "ALPHA_EXECUTION_MODE",
    ):
        assert var in text, f"{var} not documented in .env.example"

    # every assignment must be empty or a safe non-secret default
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip().startswith("KRAKEN") or key.strip().startswith("TELEGRAM"):
            assert value.strip() == "", f"{key.strip()} must ship empty, got {value!r}"


def test_env_example_is_not_gitignored() -> None:
    """`.env.*` is ignored, so `!.env.example` must negate it or the file is lost."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "!.env.example" in gitignore, ".env.example would be swallowed by the .env.* rule"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
