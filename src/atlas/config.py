"""Runtime settings, read from environment variables / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LIVE_TRADING_CONFIRMATION = "I_UNDERSTAND_THIS_USES_REAL_MONEY"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="ATLAS_", extra="ignore")

    config_dir: Path = Path("config")
    database_url: str = "postgresql+psycopg://atlas:atlas@localhost:5432/atlas"
    redis_url: str = "redis://localhost:6379/0"

    anthropic_api_key: SecretStr | None = None
    daily_llm_budget_usd: float = 20.0

    kill_switch: bool = False
    live_trading: bool = False
    live_trading_confirm: str = ""

    base_currency: str = "USD"

    @property
    def live_trading_enabled(self) -> bool:
        """Live trading needs both the flag and the explicit confirmation phrase."""
        return (
            self.live_trading
            and not self.kill_switch
            and self.live_trading_confirm == LIVE_TRADING_CONFIRMATION
        )
