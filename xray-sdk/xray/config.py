"""
X-Ray SDK Configuration

This module manages SDK configuration settings like API URL, fallback modes, etc.
Uses Pydantic for validation and environment variable support.

Reference: IMPLEMENTATION_PLAN.md -> "Developer Experience: Progressive Instrumentation" -> "Failure Handling"
"""

import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# ENUMS - Configuration Options
# =============================================================================


class FallbackMode(str, Enum):
    """
    What to do when the X-Ray API is unavailable.

    - SILENT: No-op, continue normally (production default)
    - LOG: Write traces to local file for later upload
    - RAISE: Raise exception (useful for testing)

    Reference: IMPLEMENTATION_PLAN.md -> Failure Handling
    """

    SILENT = "silent"
    LOG = "log"
    RAISE = "raise"


# =============================================================================
# XRAY CONFIGURATION
# =============================================================================


class XRayConfig(BaseModel):
    """
    Configuration for the X-Ray SDK.

    Can be set programmatically or via environment variables.

    Example usage:
        # Programmatic configuration
        from xray import configure
        configure(
            api_url="http://localhost:8000",
            fallback_mode="log",
            enabled=True
        )

        # Or use environment variables:
        # export XRAY_API_URL=http://localhost:8000
        # export XRAY_ENABLED=true
        # export XRAY_FALLBACK_MODE=log

    Reference: IMPLEMENTATION_PLAN.md -> "Developer Experience"
    """

    # Core settings
    api_url: str = Field(
        default=os.getenv("XRAY_API_URL", "http://localhost:8000"),
        description="URL of the X-Ray API server",
    )

    enabled: bool = Field(
        default=os.getenv("XRAY_ENABLED", "true").lower() == "true",
        description="Enable/disable X-Ray tracing globally",
    )

    # Failure handling
    fallback_mode: FallbackMode = Field(
        default=FallbackMode(os.getenv("XRAY_FALLBACK_MODE", "silent")),
        description="What to do when API is unavailable",
    )

    fallback_log_path: str = Field(
        default=os.getenv("XRAY_FALLBACK_LOG_PATH", ".xray/failed_traces/"),
        description="Where to write traces when using 'log' fallback mode",
    )

    # Performance settings
    timeout_seconds: float = Field(
        default=float(os.getenv("XRAY_TIMEOUT", "5.0")),
        description="HTTP request timeout in seconds",
        gt=0,
        le=60,
    )

    async_mode: bool = Field(
        default=os.getenv("XRAY_ASYNC_MODE", "true").lower() == "true",
        description="Send traces asynchronously (non-blocking)",
    )

    # Sampling settings (for future use with smart sampling)
    max_candidates_full_capture: int = Field(
        default=int(os.getenv("XRAY_MAX_CANDIDATES_FULL", "100")),
        description="Capture all candidates if count <= this",
        gt=0,
    )

    sample_size_large: int = Field(
        default=int(os.getenv("XRAY_SAMPLE_SIZE_LARGE", "50")),
        description="Sample size for large candidate sets (>1000)",
        gt=0,
    )

    sample_size_medium: int = Field(
        default=int(os.getenv("XRAY_SAMPLE_SIZE_MEDIUM", "100")),
        description="Sample size for medium candidate sets (100-1000)",
        gt=0,
    )

    # Debug settings
    verbose: bool = Field(
        default=os.getenv("XRAY_VERBOSE", "false").lower() == "true",
        description="Enable verbose logging for debugging",
    )

    @field_validator("api_url")
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        """Ensure API URL doesn't have trailing slash"""
        return v.rstrip("/")

    model_config = {
        "json_schema_extra": {
            "example": {
                "api_url": "http://localhost:8000",
                "enabled": True,
                "fallback_mode": "silent",
                "timeout_seconds": 5.0,
                "async_mode": True,
                "verbose": False,
            }
        }
    }


# =============================================================================
# GLOBAL CONFIGURATION INSTANCE
# =============================================================================

# Singleton configuration instance
_config: Optional[XRayConfig] = None


def get_config() -> XRayConfig:
    """
    Get the current X-Ray configuration.

    Creates a default configuration if none exists.

    Returns:
        Current XRayConfig instance

    Example:
        config = get_config()
        print(config.api_url)
    """
    global _config
    if _config is None:
        _config = XRayConfig()
    return _config


def configure(**kwargs) -> XRayConfig:
    """
    Configure the X-Ray SDK.

    This is the main way users configure X-Ray.

    Args:
        **kwargs: Configuration options (see XRayConfig fields)

    Returns:
        Updated XRayConfig instance

    Example:
        from xray import configure

        # For production (silent failures)
        configure(
            api_url="https://xray.company.com",
            fallback_mode="silent",
            enabled=True
        )

        # For development (log failures)
        configure(
            api_url="http://localhost:8000",
            fallback_mode="log",
            verbose=True
        )

        # For testing (raise on failures)
        configure(
            api_url="http://localhost:8000",
            fallback_mode="raise",
            enabled=True
        )

        # Disable X-Ray entirely
        configure(enabled=False)
    """
    global _config

    if _config is None:
        # Create new config with provided settings
        _config = XRayConfig(**kwargs)
    else:
        # Update existing config
        for key, value in kwargs.items():
            if hasattr(_config, key):
                setattr(_config, key, value)
            else:
                raise ValueError(f"Unknown configuration option: {key}")

    return _config


def reset_config() -> None:
    """
    Reset configuration to defaults.

    Useful for testing.

    Example:
        # In a test
        reset_config()
        configure(api_url="http://test:8000")
    """
    global _config
    _config = None


def is_enabled() -> bool:
    """
    Check if X-Ray tracing is enabled.

    Returns:
        True if enabled, False otherwise

    Example:
        if is_enabled():
            with RunContext("my_pipeline") as run:
                # ... tracing code
        else:
            # Skip tracing
            pass
    """
    return get_config().enabled
