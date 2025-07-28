"""
Configuration for FunkyGibbon.
"""

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./funkygibbon.db",
        env="DATABASE_URL"
    )
    database_echo: bool = Field(default=False, env="DATABASE_ECHO")
    
    # API
    api_host: str = Field(default="0.0.0.0", env="API_HOST")
    api_port: int = Field(default=8000, env="API_PORT")
    api_prefix: str = Field(default="/api/v1", env="API_PREFIX")
    
    # Security
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        env="SECRET_KEY"
    )
    api_key: Optional[str] = Field(default=None, env="API_KEY")
    
    # Sync
    sync_batch_size: int = Field(default=50, env="SYNC_BATCH_SIZE")
    sync_conflict_strategy: str = Field(default="last_write_wins", env="SYNC_CONFLICT_STRATEGY")
    
    # Performance
    max_entities_per_house: int = Field(default=300, env="MAX_ENTITIES_PER_HOUSE")
    max_users_per_house: int = Field(default=10, env="MAX_USERS_PER_HOUSE")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()