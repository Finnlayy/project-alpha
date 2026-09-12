"""
=========================================================
Datei:      app/telegram/TelegramBotEngine.py (v1.7.0)
Zweck:      Telegram Bot & WebApp Challenge Buttons & Alerts
Knoten:     Jaune (Carrera-Engine) / Alerting & 2FA Gate
System:     "The Judge & The Swarm" - Zero-Dummy Guarantee
=========================================================
"""
from __future__ import annotations
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.telegram.bot_engine")


@dataclass
class PendingTwoFactorChallenge:
    challenge_id: str
    admin_id: str
    action: str
    verification_code: str
    details: Dict[str, Any]
    created_at: float
    expires_at: float


class TelegramBotEngine:
    """
    Verbindet das Trading-System mit Telegram für Echtzeit-Alarmierungen,
    zwei-Wege WebApp-Challenge-Buttons (M8 Gate Freigaben) und 2FA-Autopsien.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        default_chat_id: Optional[str] = None,
        webapp_url: Optional[str] = None
    ):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.default_chat_id = default_chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.webapp_url = webapp_url or os.environ.get("TELEGRAM_WEBAPP_URL", "https://ais-dev-ngng2enll4ife5vqpezczt-240906819449.europe-west3.run.app")
        self.active_challenges: Dict[str, PendingTwoFactorChallenge] = {}

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.default_chat_id)

    def _send_telegram_request(self, method_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Führt einen HTTPS-Request an die offizielle Telegram Bot API durch."""
        if not self.bot_token:
            logger.info("Telegram-Token nicht konfiguriert; Mock-Ausführung von '%s': %s", method_name, payload)
            return {"ok": True, "simulated": True, "result": payload}

        api_url = f"https://api.telegram.org/bot{self.bot_token}/{method_name}"
        headers = {"Content-Type": "application/json"}
        req_body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(api_url, data=req_body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                resp_bytes = response.read()
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            logger.error("Telegram API HTTPError (%d): %s", e.code, err_msg)
            return {"ok": False, "error": err_msg, "code": e.code}
        except Exception as e:
            logger.error("Netzwerkfehler beim Senden an Telegram: %s", e)
            return {"ok": False, "error": str(e)}

    def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "HTML",
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Sendet eine formattierte Textnachricht an einen Chat oder Kanal."""
        target_chat = chat_id or self.default_chat_id
        if not target_chat:
            logger.warning("Keine Chat-ID für Telegram vorhanden.")
            return {"ok": False, "error": "Missing chat_id"}

        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        return self._send_telegram_request("sendMessage", payload)

    def create_webapp_challenge_keyboard(
        self,
        challenge_id: str,
        prompt_text: str = "🔓 M8 Gate Challenge Freigeben"
    ) -> Dict[str, Any]:
        """
        Erstellt ein Telegram Inline-Keyboard mit WebApp Button.
        Ermöglicht dem Trader, im Telegram-Client eine biometrische Passkey-Validierung
        über die integrierte WebApp auszulösen.
        """
        url_with_param = f"{self.webapp_url}?challenge_id={challenge_id}"
        return {
            "inline_keyboard": [
                [
                    {
                        "text": prompt_text,
                        "web_app": {"url": url_with_param}
                    }
                ],
                [
                    {
                        "text": "🛑 Abbruch & Quarantäne",
                        "callback_data": f"abort_challenge:{challenge_id}"
                    }
                ]
            ]
        }

    def issue_execution_challenge(
        self,
        admin_id: str,
        action: str,
        details: Dict[str, Any],
        ttl_seconds: int = 180
    ) -> str:
        """
        Initiiert eine Zwei-Faktor-Freigabe für kritische Eingriffe (z.B. M8 Gate Override,
        Kapitalallokations-Boost oder Notfall-Stopp).
        """
        challenge_id = f"chal_tg_{secrets.token_hex(6)}"
        verification_code = f"{secrets.randbelow(900000) + 100000}"
        now = time.time()

        record = PendingTwoFactorChallenge(
            challenge_id=challenge_id,
            admin_id=admin_id,
            action=action,
            verification_code=verification_code,
            details=details,
            created_at=now,
            expires_at=now + ttl_seconds
        )
        self.active_challenges[challenge_id] = record

        # Nachricht an Telegram senden
        msg = (
            f"<b>⚠️ M8 GATE SECURITY CHALLENGE</b>\n\n"
            f"<b>Aktion:</b> {action}\n"
            f"<b>Details:</b> {json.dumps(details, indent=2)}\n"
            f"<b>2FA-Code:</b> <code>{verification_code}</code>\n"
            f"<b>Gültigkeit:</b> {ttl_seconds} Sekunden\n\n"
            f"Klicke auf den Button unten, um die Freigabe per WebApp/Passkey zu bestätigen."
        )

        markup = self.create_webapp_challenge_keyboard(challenge_id)
        self.send_message(text=msg, reply_markup=markup)

        return challenge_id

    def verify_execution_challenge(self, challenge_id: str, submitted_code: str) -> bool:
        """Überprüft den 2FA-Code oder die WebApp-Bestätigung."""
        challenge = self.active_challenges.get(challenge_id)
        if not challenge:
            return False

        if time.time() > challenge.expires_at:
            self.active_challenges.pop(challenge_id, None)
            return False

        if hmac.compare_digest(challenge.verification_code.strip(), submitted_code.strip()):
            self.active_challenges.pop(challenge_id, None)
            logger.info("Telegram 2FA Challenge %s erfolgreich verifiziert.", challenge_id)
            return True

        return False

    def notify_trade_executed(
        self,
        symbol: str,
        direction: str,
        size_contracts: float,
        entry_price: float,
        leverage: float,
        strategy_id: str
    ) -> Dict[str, Any]:
        """Sendet einen formatierten Trade-Execution Alert."""
        icon = "🟢" if direction.upper() in ("LONG", "BUY") else "🔴"
        text = (
            f"{icon} <b>TRADE AUSGEFÜHRT: {symbol}</b>\n"
            f"• Richtung: <b>{direction.upper()}</b>\n"
            f"• Einstieg: <b>${entry_price:,.2f}</b>\n"
            f"• Kontrakte: <code>{size_contracts}</code>\n"
            f"• Hebel: <b>{leverage}x</b>\n"
            f"• Strategie: <i>{strategy_id}</i>"
        )
        return self.send_message(text)

    def notify_m8_gate_state_change(
        self,
        instance_id: str,
        old_status: str,
        new_status: str,
        current_budget_usd: float
    ) -> Dict[str, Any]:
        """Sendet einen Alert bei Statusänderungen der M8 State Machine."""
        status_emoji = {
            "ACTIVE": "🟢",
            "THROTTLED": "🟡",
            "QUARANTINED": "🚨"
        }.get(new_status, "⚪")

        text = (
            f"{status_emoji} <b>M8 GATE STATUSWECHSEL</b>\n"
            f"• Instanz: <code>{instance_id}</code>\n"
            f"• Übergang: <b>{old_status} ➔ {new_status}</b>\n"
            f"• Rest-Budget: <b>${current_budget_usd:.2f}</b>"
        )
        return self.send_message(text)

    def notify_swarm_bot_spawned(
        self,
        bot_id: str,
        historical_source_id: str,
        pair: str,
        leverage: float,
        allocated_capital: float
    ) -> Dict[str, Any]:
        """Informiert über einen neu gespawnten Swarm Worker Bot."""
        text = (
            f"🤖 <b>SWARM WORKER BOT GESPAWNT</b>\n"
            f"• Bot-ID: <code>{bot_id}</code>\n"
            f"• Vorbild-Session: <code>{historical_source_id}</code>\n"
            f"• Paar: <b>{pair}</b>\n"
            f"• Hebel: <b>{leverage}x</b>\n"
            f"• Allokiertes Kapital: <b>${allocated_capital:,.2f}</b>"
        )
        return self.send_message(text)
