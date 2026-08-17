from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CONTRAIL_")

    host: str = "0.0.0.0"
    port: int = 8000
    weather_provider: Literal["gfs_pycontrails", "open_meteo"] = "gfs_pycontrails"
    weather_cache_dir: str = "/tmp/skyprint_weather_cache"
    weather_cache_ttl_hours: int = 12
    open_meteo_base_url: str = "https://api.open-meteo.com/v1/gfs"
    cors_origins: list[str] = ["http://localhost:3000"]
    fallback_only: bool = False
    log_level: str = "INFO"


settings = Settings()
