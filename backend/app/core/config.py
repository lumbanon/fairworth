from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+psycopg://fairworth:fairworth_local@127.0.0.1:5440/fairworth"
    sec_user_agent: str = ""
    sec_min_interval_seconds: float = Field(default=0.2, ge=0.1)
    provider_timeout_seconds: float = Field(default=20, ge=1, le=120)
    provider_retries: int = Field(default=2, ge=0, le=5)
    market_data_provider: str = "disabled"
    fmp_api_key: str = ""
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    sec_cache_ttl_seconds: int = Field(default=21600, ge=1)
    company_cache_ttl_seconds: int = Field(default=86400, ge=1)
    market_cache_ttl_seconds: int = Field(default=300, ge=1)
    historical_cache_ttl_seconds: int = Field(default=3600, ge=1)
    market_max_age_seconds: int = Field(default=172800, ge=1)
    api_history_limit: int = Field(default=365, ge=1, le=2000)
    valuation_input_cache_seconds: int = Field(default=60, ge=1, le=300)
    valuation_calculation_timeout_seconds: float = Field(default=8, ge=1, le=30)
    valuation_forecast_years: int = Field(default=5, ge=1, le=20)
    valuation_terminal_growth: float = Field(default=0.02, ge=-0.05, le=0.05)
    valuation_benchmark_cost_of_equity: float = Field(default=0.10, gt=0, le=0.5)
    valuation_allow_benchmark_cost_of_equity: bool = True

    @field_validator("cors_origins")
    @classmethod
    def validate_origins(cls, values):
        if any("*" in value or not value.startswith(("http://", "https://")) for value in values):
            raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins.")
        return values

    @field_validator("market_data_provider")
    @classmethod
    def validate_provider(cls, value):
        value = value.lower()
        if value not in {"disabled", "fmp"}:
            raise ValueError("MARKET_DATA_PROVIDER must be disabled or fmp.")
        return value


@lru_cache
def get_settings():
    return Settings()
