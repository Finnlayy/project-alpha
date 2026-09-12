"""
Central runtime configuration for the Projekt:Alpha execution backend.
All values come from environment variables (or .env) — nothing is hardcoded,
nothing is simulated. When credentials are absent the system reports
'offline'/'unconfigured' states explicitly instead of fabricating data.
"""
from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional .env support without external deps
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("ALPHA_DATA_DIR", str(ROOT_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass
class KrakenCredentials:
    api_key: str = ""
    api_secret: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.api_secret)

    @property
    def key_preview(self) -> str:
        if not self.api_key:
            return ""
        k = self.api_key.strip()
        return f"{k[:4]}••••{k[-4:]}" if len(k) > 8 else "••••••••"


@dataclass
class Settings:
    # --- Kraken credentials (real env vars, never simulated) ---
    spot: KrakenCredentials = field(default_factory=KrakenCredentials)
    futures: KrakenCredentials = field(default_factory=KrakenCredentials)

    # --- Mode: 'paper' (default) or 'live' ---
    execution_mode: str = "paper"

    # --- Endpoints ---
    spot_rest: str = "https://api.kraken.com"
    futures_rest: str = "https://futures.kraken.com"
    ws_url: str = "wss://ws.kraken.com/v2"
    request_timeout: float = 10.0

    # --- Storage ---
    db_path: str = str(DATA_DIR / "lake.duckdb")

    # --- Auth ---
    rp_id: str = "projekt-alpha.local"
    allowed_origins: list = field(default_factory=list)
    session_key_file: str = str(DATA_DIR / "session.key")
    session_ttl_seconds: int = 86400
    challenge_ttl_seconds: int = 120

    # --- Market data ---
    tracked_symbols: list = field(default_factory=lambda: ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD"])
    default_interval: int = 5  # minutes

    # --- Execution ---
    min_poll_seconds: float = 5.0
    initial_paper_balance_usd: float = 10000.0
    base_budget_usd: float = 100.0  # per M8 instance, per blueprint example
    live_order_2fa: bool = True

    # --- Telegram (optional notifications / 2FA) ---
    telegram_token: str = ""
    telegram_chat_id: str = ""

    # --- Misc ---
    started_at: float = field(default_factory=time.time)

    @property
    def uptime(self) -> int:
        return int(time.time() - self.started_at)

    def uptime_hms(self) -> str:
        s = self.uptime
        return f"{s // 3600:02d}h {(s % 3600) // 60:02d}m {s % 60:02d}s"


def load_settings() -> Settings:
    settings = Settings()
    settings.spot.api_key = _env("KRAKEN_SPOT_API_KEY") or _env("KRAKEN_API_KEY")
    settings.spot.api_secret = _env("KRAKEN_SPOT_PRIVATE_KEY") or _env("KRAKEN_PRIVATE_KEY")
    settings.futures.api_key = _env("KRAKEN_FUTURES_API_KEY") or _env("KRAKEN_PRO_API_KEY")
    settings.futures.api_secret = _env("KRAKEN_FUTURES_PRIVATE_KEY") or _env("KRAKEN_PRO_PRIVATE_KEY")
    settings.execution_mode = _env("ALPHA_EXECUTION_MODE", "paper").lower()
    if settings.execution_mode not in ("paper", "live"):
        settings.execution_mode = "paper"
    settings.db_path = _env("ALPHA_DB_PATH", settings.db_path)
    settings.rp_id = _env("ALPHA_RP_ID", settings.rp_id)
    origins = _env("ALPHA_ALLOWED_ORIGINS", "")
    settings.allowed_origins = [o.strip() for o in origins.split(",") if o.strip()]
    settings.session_ttl_seconds = _env_int("ALPHA_SESSION_TTL", settings.session_ttl_seconds)
    settings.tracked_symbols = [s.strip() for s in _env("ALPHA_SYMBOLS", "BTC/USD,ETH/USD,SOL/USD,XRP/USD").split(",") if s.strip()]
    settings.default_interval = _env_int("ALPHA_DEFAULT_INTERVAL", settings.default_interval)
    settings.min_poll_seconds = _env_float("ALPHA_MIN_POLL_SECONDS", settings.min_poll_seconds)
    settings.initial_paper_balance_usd = _env_float("ALPHA_PAPER_BALANCE", settings.initial_paper_balance_usd)
    settings.base_budget_usd = _env_float("ALPHA_BASE_BUDGET", settings.base_budget_usd)
    settings.telegram_token = _env("TELEGRAM_BOT_TOKEN")
    settings.telegram_chat_id = _env("TELEGRAM_CHAT_ID")
    return settings


def get_session_secret(settings: Settings) -> str:
    """Persistent HMAC secret for session tokens (created once, 0600)."""
    path = Path(settings.session_key_file)
    if path.exists():
        return path.read_text().strip()
    secret = secrets.token_hex(32)
    path.write_text(secret)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return secret
