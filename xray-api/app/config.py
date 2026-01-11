"""
X-Ray API Configuration

Manages API settings using Pydantic Settings.
Reads from environment variables with fallback defaults.

Reference: IMPLEMENTATION_PLAN.md -> "API Backend Architecture"
"""

import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """
    API configuration settings.

    All settings can be overridden via environment variables:
    - DATABASE_URL: PostgreSQL connection string
    - API_HOST: Host to bind to
    - API_PORT: Port to listen on
    - LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
    """

    # Database
    database_url: str = Field(
        default=os.getenv(
            "DATABASE_URL",
            "postgresql://animeshdhillon@localhost:5432/xray_db"
        ),
        description="PostgreSQL connection string"
    )

    # API Server
    api_host: str = Field(
        default=os.getenv("API_HOST", "0.0.0.0"),
        description="Host to bind to"
    )

    api_port: int = Field(
        default=int(os.getenv("API_PORT", "8000")),
        description="Port to listen on"
    )

    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins"
    )

    # Logging
    log_level: str = Field(
        default=os.getenv("LOG_LEVEL", "INFO"),
        description="Logging level"
    )

    # Application
    app_name: str = "X-Ray API"
    app_version: str = "0.1.0"
    app_description: str = "API for storing and querying X-Ray pipeline traces"

    # Pagination
    default_page_size: int = 50
    max_page_size: int = 1000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
