"""
FunkyGibbon - Configuration Management

DEVELOPMENT CONTEXT:
Created in January 2024 as the central configuration module for FunkyGibbon.
Designed to support both development and production environments through
environment variables, with sensible defaults for single-house deployments.

FUNCTIONALITY:
- Centralizes all application configuration using Pydantic Settings
- Loads configuration from environment variables and .env files
- Provides type-safe configuration with validation
- Defines limits based on single-house scale (300 entities, 10 users)
- Manages database, API, security, sync, and performance settings

PURPOSE:
Single source of truth for all configuration values across the application.
This ensures consistency, type safety, and easy environment-specific overrides
without hardcoding values throughout the codebase.

KNOWN ISSUES:
- Default secret key is insecure and must be changed in production
- SQLite database path is relative, which can cause issues with working directories
- No configuration validation for production deployment (e.g., secure secret key)
- Database echo can impact performance if accidentally left on in production

REVISION HISTORY:
- 2024-01-15: Initial implementation with basic settings
- 2024-01-16: Added sync configuration for conflict resolution
- 2024-01-17: Added performance limits for single-house scale
- 2024-01-18: Switched to Pydantic Settings v2 syntax

DEPENDENCIES:
- pydantic_settings: For environment variable loading and validation
- pydantic: For configuration model and field validation
- pathlib: For path handling (though not fully utilized yet)

USAGE:
from funkygibbon.config import settings
print(f"API running on {settings.api_host}:{settings.api_port}")
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