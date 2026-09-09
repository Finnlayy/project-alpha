"""
=========================================================
Datei:      app/security/SettingsEnvManager.py (v1.7.0)
Zweck:      Full CRUD, Dual-Key Validation & Hot-Reload für `.env`-Variablen in der App UI
Knoten:     Jaune (Carrera-Engine) / Security & Vault Gate
=========================================================
"""
import os
import re
import logging
from typing import Dict, Any, Optional, Tuple, NamedTuple

logger = logging.getLogger("app.security.settings_manager")

class KrakenKeyStatus(NamedTuple):
    key_name: str
    is_present: bool
    masked_preview: Optional[str]
    api_target: str
    description: str

class SettingsEnvManager:
    """
    Verwaltet das Laden, Prüfen und Maskieren von Umgebungsvariablen mit strikter
    Unterstützung für das Kraken Dual-Key-System (Spot-Trading-API vs. Futures-Trading-API).
    """

    SPOT_API_KEY_VARS = ["KRAKEN_SPOT_API_KEY", "KRAKEN_API_KEY"]
    SPOT_SECRET_VARS = ["KRAKEN_SPOT_PRIVATE_KEY", "KRAKEN_PRIVATE_KEY"]
    
    FUTURES_API_KEY_VARS = ["KRAKEN_FUTURES_API_KEY", "KRAKEN_PRO_API_KEY"]
    FUTURES_SECRET_VARS = ["KRAKEN_FUTURES_PRIVATE_KEY", "KRAKEN_PRO_PRIVATE_KEY"]

    def __init__(self, env_path: Optional[str] = None):
        self.env_path = env_path or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", ".env")
        )
        self.example_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", ".env.example")
        )

    @staticmethod
    def mask_key(secret: Optional[str]) -> Optional[str]:
        """Maskiert einen API-Key sicher für die Frontend-Übertragung (z.B. 9sPO••••vjo8Z)."""
        if not secret:
            return None
        secret_clean = secret.strip()
        if len(secret_clean) <= 8:
            return "••••••••"
        return f"{secret_clean[:4]}••••{secret_clean[-4:]}"

    def get_kraken_spot_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """Liest den Kraken Spot API-Key und Private Key aus Umgebungsvariablen."""
        api_key = None
        for var_name in self.SPOT_API_KEY_VARS:
            val = os.environ.get(var_name)
            if val and val.strip():
                api_key = val.strip()
                break

        secret = None
        for var_name in self.SPOT_SECRET_VARS:
            val = os.environ.get(var_name)
            if val and val.strip():
                secret = val.strip()
                break

        return api_key, secret

    def get_kraken_futures_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """Liest den Kraken Pro / Futures API-Key und Private Key aus Umgebungsvariablen."""
        api_key = None
        for var_name in self.FUTURES_API_KEY_VARS:
            val = os.environ.get(var_name)
            if val and val.strip():
                api_key = val.strip()
                break

        secret = None
        for var_name in self.FUTURES_SECRET_VARS:
            val = os.environ.get(var_name)
            if val and val.strip():
                secret = val.strip()
                break

        return api_key, secret

    def get_credentials_status(self) -> Dict[str, Any]:
        """
        Gibt den vollständigen Konfigurationsstatus beider Kraken-API-Schlüsselgruppen zurück.
        Kryptografische Secrets werden NIEMALS unmaskiert zurückgegeben.
        """
        spot_key, spot_sec = self.get_kraken_spot_credentials()
        fut_key, fut_sec = self.get_kraken_futures_credentials()

        has_spot = bool(spot_key and spot_sec)
        has_futures = bool(fut_key and fut_sec)

        return {
            "hasSpotCredentials": has_spot,
            "hasFuturesCredentials": has_futures,
            "bothConfigured": has_spot and has_futures,
            "anyConfigured": has_spot or has_futures,
            "spot": {
                "configured": has_spot,
                "keyPreview": self.mask_key(spot_key) if has_spot else "9sPO••••vjo8Z (sim)",
                "source": "env" if has_spot else "simulated",
                "apiDomain": "api.kraken.com",
                "displayName": "Spot-Trading-API",
                "description": "Spot- und Margin-Trading, Fiat-Guthaben (EUR/USD), Cash Funding",
                "permissions": ["Query Funds", "Query Open Orders & Trades", "Create & Modify Orders"]
            },
            "futures": {
                "configured": has_futures,
                "keyPreview": self.mask_key(fut_key) if has_futures else "7EG7••••JToFpf+ (sim)",
                "source": "env" if has_futures else "simulated",
                "apiDomain": "futures.kraken.com",
                "displayName": "Futures-Trading-API (Kraken Pro)",
                "description": "Perpetual Swaps (PF_XBTUSD, PF_ETHUSD), Derivatives Margin & Liquidation Risk",
                "permissions": ["Allgemeine API (Voller Zugriff)", "Positionen & Margin Read/Write"]
            }
        }

    def read_env_file(self) -> Dict[str, str]:
        """Liest die .env Datei und extrahiert Schlüssel-Wert-Paare."""
        result: Dict[str, str] = {}
        target_path = self.env_path if os.path.exists(self.env_path) else self.example_path
        if not os.path.exists(target_path):
            return result

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        result[k.strip()] = v.strip().strip("\"'")
        except Exception as e:
            logger.error("Fehler beim Lesen der .env-Datei %s: %s", target_path, e)
        return result
