"""
X-Ray SDK - Public API

This module exports the public interface for the X-Ray SDK.
Users can import everything they need from the top-level xray package.

Usage:
    from xray import configure, RunContext
    from xray.models import StepType

    configure(api_url="http://localhost:8000")

    with RunContext("my_pipeline") as run:
        with run.step("step1", StepType.LLM) as step:
            result = do_work()
            step.set_outputs(result)

Reference: IMPLEMENTATION_PLAN.md -> "Developer Experience"
"""

# =============================================================================
# PUBLIC API - Core functionality
# =============================================================================

# Configuration
from .config import (
    FallbackMode,
    XRayConfig,
    configure,
    get_config,
    is_enabled,
    reset_config,
)

# Context Managers
from .context import (
    RunContext,
    StepContext,
    get_current_run,
    get_current_step,
)

# Data Models
from .models import (
    IngestPayload,
    RunModel,
    RunStatus,
    StepModel,
    StepType,
)

# HTTP Client (advanced usage)
from .client import (
    XRayClient,
    send_trace,
)

# =============================================================================
# VERSION
# =============================================================================

__version__ = "0.1.0"

# =============================================================================
# PUBLIC EXPORTS
# =============================================================================

__all__ = [
    # Configuration
    "configure",
    "get_config",
    "is_enabled",
    "reset_config",
    "FallbackMode",
    "XRayConfig",
    # Context Managers (most commonly used)
    "RunContext",
    "StepContext",
    "get_current_run",
    "get_current_step",
    # Data Models
    "RunModel",
    "StepModel",
    "IngestPayload",
    "RunStatus",
    "StepType",
    # HTTP Client (advanced usage)
    "XRayClient",
    "send_trace",
    # Version
    "__version__",
]
