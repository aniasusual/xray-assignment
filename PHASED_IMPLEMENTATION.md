# X-Ray SDK & API - Phased Implementation Guide

This document breaks down the project into small, manageable phases. Complete each phase before moving to the next.

---

## 📊 Phase Overview

| Phase | Focus | Time | Output |
|-------|-------|------|--------|
| **Phase 0** | Project Setup | 30 min | Folder structure, dependencies |
| **Phase 1** | SDK Data Models | 1 hour | Pydantic models for Run/Step |
| **Phase 2** | SDK Context Management | 1.5 hours | Context managers with timing |
| **Phase 3** | SDK Configuration | 30 min | Config system with fallbacks |
| **Phase 4** | SDK HTTP Client | 1 hour | API client with retry logic |
| **Phase 5** | SDK Sampling | 45 min | Smart sampling strategies |
| **Phase 6** | SDK Public API | 30 min | Clean public interface |
| **Phase 7** | API Database Setup | 1 hour | PostgreSQL + SQLAlchemy models |
| **Phase 8** | API Schemas | 45 min | Pydantic request/response schemas |
| **Phase 9** | API Ingest Endpoint | 1 hour | POST /api/v1/runs/ingest |
| **Phase 10** | API Query Endpoints | 1.5 hours | GET runs, filter, search |
| **Phase 11** | Integration Test | 1 hour | SDK → API → DB end-to-end |
| **Phase 12** | Demo Example 1 | 1.5 hours | Competitor selection with bug |
| **Phase 13** | Demo Example 2 | 1 hour | Query/debugging script |
| **Phase 14** | Architecture Doc | 2.5 hours | Complete ARCHITECTURE.md |
| **Phase 15** | Video & Polish | 1.5 hours | Record, README, cleanup |

**Total Time**: ~16 hours

---

## Phase 0: Project Setup 🏗️

**Goal**: Create project structure and install dependencies.

**Duration**: 30 minutes

### Tasks

#### 1. Create Directory Structure
```bash
cd /Users/animeshdhillon/myProjects/xray-assignment

# Create SDK structure
mkdir -p xray-sdk/xray
mkdir -p xray-sdk/tests

# Create API structure
mkdir -p xray-api/app/routers
mkdir -p xray-api/app/services
mkdir -p xray-api/tests

# Create examples structure
mkdir -p examples/shared

# Create docs structure
mkdir -p docs/diagrams
```

#### 2. Initialize SDK with Poetry
```bash
cd xray-sdk

# Initialize Poetry project
poetry init --name xray-sdk --description "X-Ray SDK for debugging multi-step pipelines" --author "Your Name <your.email@example.com>" --python "^3.9" --no-interaction

# Add dependencies
poetry add httpx pydantic python-dateutil

# Add dev dependencies
poetry add --group dev pytest pytest-asyncio pytest-mock black mypy
```

#### 3. Initialize API with Poetry
```bash
cd ../xray-api

# Initialize Poetry project
poetry init --name xray-api --description "X-Ray API for storing and querying traces" --author "Your Name <your.email@example.com>" --python "^3.9" --no-interaction

# Add dependencies
poetry add fastapi uvicorn[standard] sqlalchemy psycopg2-binary alembic pydantic-settings python-dateutil

# Add dev dependencies
poetry add --group dev pytest pytest-asyncio httpx black mypy
```

#### 4. Create Initial Files
```bash
cd ..

# SDK files
touch xray-sdk/xray/__init__.py
touch xray-sdk/xray/models.py
touch xray-sdk/xray/context.py
touch xray-sdk/xray/config.py
touch xray-sdk/xray/client.py
touch xray-sdk/xray/sampling.py

# API files
touch xray-api/app/__init__.py
touch xray-api/app/main.py
touch xray-api/app/config.py
touch xray-api/app/database.py
touch xray-api/app/models.py
touch xray-api/app/schemas.py
touch xray-api/app/routers/__init__.py
touch xray-api/app/routers/ingest.py
touch xray-api/app/routers/query.py
touch xray-api/app/services/__init__.py
touch xray-api/app/services/query_service.py

# Example files
touch examples/shared/__init__.py
touch examples/shared/mock_services.py
touch examples/competitor_selection.py
touch examples/query_examples.py

# Documentation
touch README.md
touch ARCHITECTURE.md
touch .gitignore
```

#### 5. Create .gitignore
```bash
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
env/
ENV/
.venv

# Poetry
poetry.lock

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/

# Database
*.db
*.sqlite3

# OS
.DS_Store
Thumbs.db

# Environment
.env
.env.local

# Logs
*.log

# X-Ray specific
.xray/
failed_traces/
EOF
```

#### 6. Setup PostgreSQL
```bash
# Install PostgreSQL (if not already installed)
brew install postgresql@14

# Start PostgreSQL
brew services start postgresql@14

# Create database
createdb xray_db
```

### Verification Checklist
- [ ] All directories created
- [ ] Poetry initialized in both SDK and API
- [ ] All dependencies installed
- [ ] Initial files created
- [ ] .gitignore configured
- [ ] PostgreSQL running
- [ ] Database created

### Success Criteria
Run these commands to verify:
```bash
cd xray-sdk && poetry --version && poetry show
cd ../xray-api && poetry --version && poetry show
psql -d xray_db -c "SELECT version();"
```

---

## Phase 1: SDK Data Models 📦

**Goal**: Create Pydantic models for Run and Step data structures.

**Duration**: 1 hour

**File**: `xray-sdk/xray/models.py`

### What to Build

Create Pydantic models that represent:
1. **RunModel**: A complete pipeline execution
2. **StepModel**: An individual step in the pipeline
3. Helper types and enums

### Implementation

```python
"""
Data models for X-Ray SDK.

These models use Pydantic for validation and serialization.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    """Status of a pipeline run."""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    RUNNING = "running"


class StepType(str, Enum):
    """Standard step types for queryability."""
    LLM = "llm"
    SEARCH = "search"
    FILTER = "filter"
    RANK = "rank"
    SELECT = "select"
    TRANSFORM = "transform"
    CUSTOM = "custom"


class StepModel(BaseModel):
    """
    Represents a single step in a pipeline execution.

    Captures decision-making context: what went in, what came out, and WHY.
    """
    id: UUID = Field(default_factory=uuid4)
    run_id: Optional[UUID] = None
    step_name: str = Field(..., min_length=1, max_length=200)
    step_type: Optional[str] = None
    sequence: int = Field(ge=0)
    start_time: datetime
    end_time: Optional[datetime] = None

    # Decision context
    inputs: Optional[Dict[str, Any]] = None
    outputs: Optional[Dict[str, Any]] = None
    reasoning: Optional[str] = None

    # Candidate tracking
    candidates_in: Optional[int] = Field(None, ge=0)
    candidates_out: Optional[int] = Field(None, ge=0)
    candidates_data: Optional[Dict[str, Any]] = None

    # Filters and metadata
    filters_applied: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }

    @property
    def duration_ms(self) -> Optional[int]:
        """Calculate step duration in milliseconds."""
        if self.end_time and self.start_time:
            delta = self.end_time - self.start_time
            return int(delta.total_seconds() * 1000)
        return None

    @property
    def reduction_rate(self) -> Optional[float]:
        """Calculate what percentage of candidates were eliminated."""
        if self.candidates_in and self.candidates_out is not None:
            if self.candidates_in == 0:
                return 0.0
            return 1.0 - (self.candidates_out / self.candidates_in)
        return None


class RunModel(BaseModel):
    """
    Represents a complete pipeline execution.

    Contains metadata about the run and aggregates all steps.
    """
    id: UUID = Field(default_factory=uuid4)
    pipeline_name: str = Field(..., min_length=1, max_length=200)
    pipeline_version: Optional[str] = Field(None, max_length=50)
    start_time: datetime
    end_time: Optional[datetime] = None
    status: RunStatus = RunStatus.RUNNING
    metadata: Optional[Dict[str, Any]] = None
    final_output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    # Steps are not included in the model itself, managed separately

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }

    @property
    def duration_ms(self) -> Optional[int]:
        """Calculate run duration in milliseconds."""
        if self.end_time and self.start_time:
            delta = self.end_time - self.start_time
            return int(delta.total_seconds() * 1000)
        return None


class IngestPayload(BaseModel):
    """
    Payload sent to the X-Ray API for ingestion.

    Contains a run and all its steps in a single request.
    """
    run: RunModel
    steps: List[StepModel] = Field(default_factory=list)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
```

### Testing

Create `xray-sdk/tests/test_models.py`:

```python
"""Tests for data models."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from xray.models import RunModel, RunStatus, StepModel, StepType, IngestPayload


def test_run_model_creation():
    """Test creating a run model."""
    run = RunModel(
        pipeline_name="test_pipeline",
        start_time=datetime.utcnow(),
        status=RunStatus.SUCCESS
    )

    assert run.id is not None
    assert run.pipeline_name == "test_pipeline"
    assert run.status == RunStatus.SUCCESS


def test_run_duration_calculation():
    """Test run duration is calculated correctly."""
    start = datetime.utcnow()
    end = start + timedelta(seconds=5)

    run = RunModel(
        pipeline_name="test",
        start_time=start,
        end_time=end,
        status=RunStatus.SUCCESS
    )

    assert run.duration_ms == 5000


def test_step_model_creation():
    """Test creating a step model."""
    step = StepModel(
        step_name="test_step",
        step_type=StepType.LLM,
        sequence=0,
        start_time=datetime.utcnow()
    )

    assert step.id is not None
    assert step.step_name == "test_step"
    assert step.step_type == StepType.LLM


def test_step_reduction_rate():
    """Test reduction rate calculation."""
    step = StepModel(
        step_name="filter",
        sequence=0,
        start_time=datetime.utcnow(),
        candidates_in=1000,
        candidates_out=100
    )

    assert step.reduction_rate == 0.9  # 90% eliminated


def test_ingest_payload():
    """Test creating an ingest payload."""
    run = RunModel(
        pipeline_name="test",
        start_time=datetime.utcnow(),
        status=RunStatus.SUCCESS
    )

    steps = [
        StepModel(
            step_name="step1",
            sequence=0,
            start_time=datetime.utcnow()
        )
    ]

    payload = IngestPayload(run=run, steps=steps)

    assert payload.run == run
    assert len(payload.steps) == 1
```

### Running Tests

```bash
cd xray-sdk
poetry run pytest tests/test_models.py -v
```

### Verification Checklist
- [ ] RunModel created with all fields
- [ ] StepModel created with all fields
- [ ] Enums defined (RunStatus, StepType)
- [ ] IngestPayload model created
- [ ] Duration calculations work
- [ ] Reduction rate calculation works
- [ ] Tests passing

---

## Phase 2: SDK Context Management 🔄

**Goal**: Implement context managers for runs and steps with automatic timing.

**Duration**: 1.5 hours

**File**: `xray-sdk/xray/context.py`

### What to Build

Create context managers that:
1. Track current run/step using contextvars (thread-safe)
2. Automatically capture start/end times
3. Support nested steps
4. Handle exceptions gracefully

### Implementation

```python
"""
Context management for X-Ray SDK.

Uses contextvars for thread-safe, async-compatible context tracking.
"""

import contextvars
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from .models import RunModel, RunStatus, StepModel


# Context variables for tracking current run and step
_current_run: contextvars.ContextVar[Optional['RunContext']] = \
    contextvars.ContextVar('current_run', default=None)

_current_step: contextvars.ContextVar[Optional['StepContext']] = \
    contextvars.ContextVar('current_step', default=None)


class StepContext:
    """
    Context manager for a pipeline step.

    Automatically captures timing and provides methods to record decision context.
    """

    def __init__(
        self,
        step_name: str,
        step_type: Optional[str] = None,
        run_context: Optional['RunContext'] = None
    ):
        self.run_context = run_context or _current_run.get()
        if not self.run_context:
            raise RuntimeError("StepContext must be used within a RunContext")

        # Get sequence number from run context
        sequence = len(self.run_context._steps)

        # Create step model
        self.step = StepModel(
            run_id=self.run_context.run.id,
            step_name=step_name,
            step_type=step_type,
            sequence=sequence,
            start_time=datetime.utcnow()
        )

        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> 'StepContext':
        """Enter the step context."""
        # Set this step as current
        self._token = _current_step.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the step context and record end time."""
        # Record end time
        self.step.end_time = datetime.utcnow()

        # Record error if exception occurred
        if exc_type is not None:
            self.step.error = f"{exc_type.__name__}: {exc_val}"

        # Reset context
        if self._token:
            _current_step.reset(self._token)

        # Add step to run context
        self.run_context._steps.append(self.step)

        # Don't suppress exceptions
        return False

    def set_inputs(self, inputs: Dict[str, Any]) -> 'StepContext':
        """Set the inputs for this step."""
        self.step.inputs = inputs
        return self

    def set_outputs(self, outputs: Any) -> 'StepContext':
        """Set the outputs for this step."""
        if not isinstance(outputs, dict):
            outputs = {"result": outputs}
        self.step.outputs = outputs
        return self

    def set_reasoning(self, reasoning: str) -> 'StepContext':
        """Set the reasoning/explanation for this step's decision."""
        self.step.reasoning = reasoning
        return self

    def set_candidates_in(self, count: int) -> 'StepContext':
        """Set the number of candidates entering this step."""
        self.step.candidates_in = count
        return self

    def set_candidates_out(self, count: int) -> 'StepContext':
        """Set the number of candidates leaving this step."""
        self.step.candidates_out = count
        return self

    def set_candidates(
        self,
        candidates: List[Any],
        capture_mode: str = "smart",
        sample_size: Optional[int] = None
    ) -> 'StepContext':
        """
        Set candidates with automatic sampling.

        Args:
            candidates: List of candidate objects
            capture_mode: "all", "summary", "sampled", or "smart"
            sample_size: Number of samples to capture (if sampled mode)
        """
        from .sampling import sample_candidates

        count = len(candidates)
        self.step.candidates_out = count

        # Use sampling module to process candidates
        self.step.candidates_data = sample_candidates(
            candidates,
            mode=capture_mode,
            sample_size=sample_size
        )

        return self

    def set_filters_applied(self, filters: Dict[str, Any]) -> 'StepContext':
        """Set the filters that were applied in this step."""
        self.step.filters_applied = filters
        return self

    def add_metadata(self, key: str, value: Any) -> 'StepContext':
        """Add metadata to this step."""
        if self.step.metadata is None:
            self.step.metadata = {}
        self.step.metadata[key] = value
        return self


class RunContext:
    """
    Context manager for a pipeline run.

    Automatically captures timing and manages steps.
    """

    def __init__(
        self,
        pipeline_name: str,
        pipeline_version: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.run = RunModel(
            pipeline_name=pipeline_name,
            pipeline_version=pipeline_version,
            start_time=datetime.utcnow(),
            metadata=metadata or {}
        )

        self._steps: List[StepModel] = []
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> 'RunContext':
        """Enter the run context."""
        # Set this run as current
        self._token = _current_run.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the run context and finalize the run."""
        # Record end time
        self.run.end_time = datetime.utcnow()

        # Set status based on exception
        if exc_type is not None:
            self.run.status = RunStatus.FAILURE
            self.run.error = f"{exc_type.__name__}: {exc_val}"
        else:
            self.run.status = RunStatus.SUCCESS

        # Reset context
        if self._token:
            _current_run.reset(self._token)

        # Send to API (will be implemented in client phase)
        self._send_to_api()

        # Don't suppress exceptions
        return False

    def step(
        self,
        step_name: str,
        step_type: Optional[str] = None
    ) -> StepContext:
        """
        Create a new step context.

        Usage:
            with run.step("keyword_generation", step_type="llm") as step:
                # ... do work
                step.set_outputs(results)
        """
        return StepContext(step_name, step_type, run_context=self)

    def set_output(self, output: Any) -> 'RunContext':
        """Set the final output of the run."""
        if not isinstance(output, dict):
            output = {"result": output}
        self.run.final_output = output
        return self

    def add_metadata(self, key: str, value: Any) -> 'RunContext':
        """Add metadata to this run."""
        if self.run.metadata is None:
            self.run.metadata = {}
        self.run.metadata[key] = value
        return self

    def _send_to_api(self):
        """Send run and steps to X-Ray API."""
        # Import here to avoid circular dependency
        from .client import get_client

        client = get_client()
        if client:
            client.send_run(self.run, self._steps)


# Utility functions

def get_current_run() -> Optional[RunContext]:
    """Get the current run context, if any."""
    return _current_run.get()


def get_current_step() -> Optional[StepContext]:
    """Get the current step context, if any."""
    return _current_step.get()
```

### Testing

Create `xray-sdk/tests/test_context.py`:

```python
"""Tests for context management."""

from datetime import datetime
import time

import pytest

from xray.context import RunContext, StepContext, get_current_run, get_current_step
from xray.models import RunStatus


def test_run_context_basic():
    """Test basic run context usage."""
    with RunContext("test_pipeline") as run:
        assert get_current_run() == run
        assert run.run.pipeline_name == "test_pipeline"
        assert run.run.start_time is not None
        assert run.run.end_time is None

    # After exiting, run should be finalized
    assert run.run.end_time is not None
    assert run.run.status == RunStatus.SUCCESS


def test_run_context_with_error():
    """Test run context handles exceptions."""
    with pytest.raises(ValueError):
        with RunContext("test_pipeline") as run:
            raise ValueError("Test error")

    assert run.run.status == RunStatus.FAILURE
    assert "ValueError" in run.run.error


def test_step_context_basic():
    """Test basic step context usage."""
    with RunContext("test_pipeline") as run:
        with run.step("test_step") as step:
            assert get_current_step() == step
            assert step.step.step_name == "test_step"
            assert step.step.sequence == 0

        # After exiting step, it should be added to run
        assert len(run._steps) == 1
        assert run._steps[0].step_name == "test_step"


def test_step_context_timing():
    """Test that step timing is captured."""
    with RunContext("test_pipeline") as run:
        with run.step("slow_step") as step:
            time.sleep(0.1)  # Sleep for 100ms

        duration = step.step.duration_ms
        assert duration is not None
        assert duration >= 100  # At least 100ms


def test_step_context_methods():
    """Test step context setter methods."""
    with RunContext("test_pipeline") as run:
        with run.step("test_step", step_type="llm") as step:
            step.set_inputs({"query": "test"})
            step.set_outputs({"result": "answer"})
            step.set_reasoning("Used GPT-4")
            step.add_metadata("model", "gpt-4")

        s = run._steps[0]
        assert s.inputs == {"query": "test"}
        assert s.outputs == {"result": "answer"}
        assert s.reasoning == "Used GPT-4"
        assert s.metadata["model"] == "gpt-4"


def test_multiple_steps():
    """Test multiple sequential steps."""
    with RunContext("test_pipeline") as run:
        with run.step("step1") as step1:
            step1.set_outputs("result1")

        with run.step("step2") as step2:
            step2.set_outputs("result2")

        with run.step("step3") as step3:
            step3.set_outputs("result3")

    assert len(run._steps) == 3
    assert run._steps[0].sequence == 0
    assert run._steps[1].sequence == 1
    assert run._steps[2].sequence == 2


def test_step_without_run_raises_error():
    """Test that step context requires a run context."""
    with pytest.raises(RuntimeError, match="must be used within a RunContext"):
        with StepContext("orphan_step"):
            pass
```

### Running Tests

```bash
cd xray-sdk
poetry run pytest tests/test_context.py -v
```

### Verification Checklist
- [ ] RunContext implemented
- [ ] StepContext implemented
- [ ] Automatic timing capture works
- [ ] Context variables for thread safety
- [ ] Nested steps supported
- [ ] Exception handling works
- [ ] All tests passing

---

## Phase 3: SDK Configuration ⚙️

**Goal**: Implement configuration system with environment variables and fallback modes.

**Duration**: 30 minutes

**File**: `xray-sdk/xray/config.py`

### Implementation

```python
"""
Configuration management for X-Ray SDK.
"""

import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FallbackMode(str, Enum):
    """Fallback behavior when API is unavailable."""
    SILENT = "silent"  # Fail silently, continue execution
    LOG = "log"        # Log to local file for later upload
    RAISE = "raise"    # Raise exception (for testing)


class XRayConfig(BaseModel):
    """Configuration for X-Ray SDK."""

    api_url: str = Field(
        default="http://localhost:8000",
        description="Base URL of the X-Ray API"
    )

    timeout: float = Field(
        default=5.0,
        ge=0.1,
        le=60.0,
        description="Timeout for API requests in seconds"
    )

    fallback_mode: FallbackMode = Field(
        default=FallbackMode.SILENT,
        description="Behavior when API is unavailable"
    )

    async_mode: bool = Field(
        default=False,
        description="Send traces asynchronously (non-blocking)"
    )

    enabled: bool = Field(
        default=True,
        description="Enable/disable X-Ray tracing"
    )

    log_file_path: str = Field(
        default=".xray/failed_traces",
        description="Path for logging failed traces (when fallback_mode=log)"
    )

    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retry attempts"
    )

    retry_backoff: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,
        description="Backoff factor for retries (exponential backoff)"
    )

    @classmethod
    def from_env(cls) -> 'XRayConfig':
        """Create config from environment variables."""
        return cls(
            api_url=os.getenv('XRAY_API_URL', 'http://localhost:8000'),
            timeout=float(os.getenv('XRAY_TIMEOUT', '5.0')),
            fallback_mode=FallbackMode(os.getenv('XRAY_FALLBACK_MODE', 'silent')),
            async_mode=os.getenv('XRAY_ASYNC_MODE', 'false').lower() == 'true',
            enabled=os.getenv('XRAY_ENABLED', 'true').lower() == 'true',
            log_file_path=os.getenv('XRAY_LOG_FILE_PATH', '.xray/failed_traces'),
            max_retries=int(os.getenv('XRAY_MAX_RETRIES', '3')),
            retry_backoff=float(os.getenv('XRAY_RETRY_BACKOFF', '1.0'))
        )


# Global configuration instance
_config: Optional[XRayConfig] = None


def configure(**kwargs) -> XRayConfig:
    """
    Configure the X-Ray SDK.

    Args:
        **kwargs: Configuration parameters (see XRayConfig)

    Returns:
        The configured XRayConfig instance

    Example:
        >>> import xray
        >>> xray.configure(
        ...     api_url="http://localhost:8000",
        ...     fallback_mode="silent",
        ...     timeout=5.0
        ... )
    """
    global _config
    _config = XRayConfig(**kwargs)
    return _config


def get_config() -> XRayConfig:
    """
    Get the current X-Ray configuration.

    If not yet configured, creates config from environment variables.
    """
    global _config
    if _config is None:
        _config = XRayConfig.from_env()
    return _config


def reset_config():
    """Reset configuration to None (mainly for testing)."""
    global _config
    _config = None
```

### Testing

Create `xray-sdk/tests/test_config.py`:

```python
"""Tests for configuration."""

import os

import pytest

from xray.config import XRayConfig, FallbackMode, configure, get_config, reset_config


def test_default_config():
    """Test default configuration values."""
    reset_config()
    config = get_config()

    assert config.api_url == "http://localhost:8000"
    assert config.timeout == 5.0
    assert config.fallback_mode == FallbackMode.SILENT
    assert config.enabled is True


def test_configure_function():
    """Test programmatic configuration."""
    reset_config()

    config = configure(
        api_url="http://api.example.com",
        timeout=10.0,
        fallback_mode=FallbackMode.RAISE
    )

    assert config.api_url == "http://api.example.com"
    assert config.timeout == 10.0
    assert config.fallback_mode == FallbackMode.RAISE


def test_config_from_env(monkeypatch):
    """Test configuration from environment variables."""
    reset_config()

    monkeypatch.setenv('XRAY_API_URL', 'http://env.example.com')
    monkeypatch.setenv('XRAY_TIMEOUT', '15.0')
    monkeypatch.setenv('XRAY_FALLBACK_MODE', 'log')
    monkeypatch.setenv('XRAY_ENABLED', 'false')

    config = XRayConfig.from_env()

    assert config.api_url == "http://env.example.com"
    assert config.timeout == 15.0
    assert config.fallback_mode == FallbackMode.LOG
    assert config.enabled is False


def test_config_validation():
    """Test that config validates input."""
    with pytest.raises(ValueError):
        XRayConfig(timeout=-1)  # Negative timeout

    with pytest.raises(ValueError):
        XRayConfig(max_retries=100)  # Too many retries
```

### Running Tests

```bash
cd xray-sdk
poetry run pytest tests/test_config.py -v
```

### Verification Checklist
- [ ] XRayConfig class with Pydantic validation
- [ ] Environment variable support
- [ ] FallbackMode enum
- [ ] configure() function
- [ ] get_config() function
- [ ] Tests passing

---

## Phase 4: SDK HTTP Client 🌐

**Goal**: Implement HTTP client for sending data to API with retry logic.

**Duration**: 1 hour

**File**: `xray-sdk/xray/client.py`

### Implementation

```python
"""
HTTP client for communicating with X-Ray API.
"""

import json
import logging
import time
from pathlib import Path
from typing import List, Optional

import httpx

from .config import FallbackMode, get_config
from .models import IngestPayload, RunModel, StepModel


logger = logging.getLogger(__name__)


class XRayClient:
    """Client for sending traces to X-Ray API."""

    def __init__(self):
        self.config = get_config()
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-load HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.config.api_url,
                timeout=self.config.timeout
            )
        return self._client

    def send_run(self, run: RunModel, steps: List[StepModel]) -> bool:
        """
        Send a run and its steps to the X-Ray API.

        Args:
            run: The run model
            steps: List of step models

        Returns:
            True if successful, False otherwise
        """
        if not self.config.enabled:
            logger.debug("X-Ray tracing is disabled, skipping send")
            return False

        # Create payload
        payload = IngestPayload(run=run, steps=steps)

        # Try to send with retries
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.client.post(
                    "/api/v1/runs/ingest",
                    json=json.loads(payload.json())
                )
                response.raise_for_status()

                logger.debug(
                    f"Successfully sent run {run.id} to X-Ray API"
                )
                return True

            except Exception as e:
                logger.warning(
                    f"Failed to send run {run.id} (attempt {attempt + 1}): {e}"
                )

                # Last attempt failed
                if attempt == self.config.max_retries:
                    return self._handle_failure(payload, e)

                # Wait before retry (exponential backoff)
                wait_time = self.config.retry_backoff * (2 ** attempt)
                time.sleep(wait_time)

        return False

    def _handle_failure(self, payload: IngestPayload, error: Exception) -> bool:
        """Handle failure based on fallback mode."""
        mode = self.config.fallback_mode

        if mode == FallbackMode.SILENT:
            logger.debug(f"Silently ignoring X-Ray send failure: {error}")
            return False

        elif mode == FallbackMode.LOG:
            return self._log_to_file(payload)

        elif mode == FallbackMode.RAISE:
            raise RuntimeError(f"Failed to send X-Ray trace: {error}") from error

        return False

    def _log_to_file(self, payload: IngestPayload) -> bool:
        """Log failed payload to file for later upload."""
        try:
            # Create directory if it doesn't exist
            log_path = Path(self.config.log_file_path)
            log_path.mkdir(parents=True, exist_ok=True)

            # Write to file (one JSON object per line)
            file_path = log_path / "failed_traces.jsonl"
            with open(file_path, 'a') as f:
                f.write(payload.json() + '\n')

            logger.info(f"Logged failed trace to {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to log trace to file: {e}")
            return False

    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __del__(self):
        """Cleanup when object is destroyed."""
        self.close()


# Global client instance
_client: Optional[XRayClient] = None


def get_client() -> Optional[XRayClient]:
    """Get the global X-Ray client instance."""
    global _client

    config = get_config()
    if not config.enabled:
        return None

    if _client is None:
        _client = XRayClient()

    return _client


def reset_client():
    """Reset the global client (mainly for testing)."""
    global _client
    if _client:
        _client.close()
    _client = None
```

### Testing

Create `xray-sdk/tests/test_client.py`:

```python
"""Tests for HTTP client."""

from datetime import datetime
from unittest.mock import Mock, patch

import httpx
import pytest

from xray.client import XRayClient, get_client, reset_client
from xray.config import FallbackMode, configure, reset_config
from xray.models import RunModel, RunStatus, StepModel


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test."""
    reset_config()
    reset_client()
    yield
    reset_config()
    reset_client()


def test_client_creation():
    """Test creating a client."""
    configure(api_url="http://test.com")
    client = get_client()

    assert client is not None
    assert client.config.api_url == "http://test.com"


def test_send_run_success(monkeypatch):
    """Test successfully sending a run."""
    configure(api_url="http://test.com")

    # Mock the HTTP client
    mock_response = Mock()
    mock_response.status_code = 201

    mock_client = Mock()
    mock_client.post.return_value = mock_response

    client = XRayClient()
    client._client = mock_client

    # Create test data
    run = RunModel(
        pipeline_name="test",
        start_time=datetime.utcnow(),
        status=RunStatus.SUCCESS
    )
    steps = [
        StepModel(
            step_name="test_step",
            sequence=0,
            start_time=datetime.utcnow()
        )
    ]

    # Send
    result = client.send_run(run, steps)

    assert result is True
    mock_client.post.assert_called_once()


def test_send_run_disabled():
    """Test that disabled config prevents sending."""
    configure(enabled=False)

    client = XRayClient()
    run = RunModel(
        pipeline_name="test",
        start_time=datetime.utcnow(),
        status=RunStatus.SUCCESS
    )

    result = client.send_run(run, [])

    assert result is False


def test_send_run_fallback_silent():
    """Test silent fallback mode."""
    configure(
        api_url="http://nonexistent.com",
        fallback_mode=FallbackMode.SILENT,
        max_retries=0,
        timeout=0.1
    )

    client = XRayClient()
    run = RunModel(
        pipeline_name="test",
        start_time=datetime.utcnow(),
        status=RunStatus.SUCCESS
    )

    # Should not raise, just return False
    result = client.send_run(run, [])
    assert result is False


def test_send_run_fallback_raise():
    """Test raise fallback mode."""
    configure(
        api_url="http://nonexistent.com",
        fallback_mode=FallbackMode.RAISE,
        max_retries=0,
        timeout=0.1
    )

    client = XRayClient()
    run = RunModel(
        pipeline_name="test",
        start_time=datetime.utcnow(),
        status=RunStatus.SUCCESS
    )

    # Should raise exception
    with pytest.raises(RuntimeError, match="Failed to send X-Ray trace"):
        client.send_run(run, [])
```

### Running Tests

```bash
cd xray-sdk
poetry run pytest tests/test_client.py -v
```

### Verification Checklist
- [ ] XRayClient class created
- [ ] send_run() method implemented
- [ ] Retry logic with exponential backoff
- [ ] Fallback modes (silent, log, raise)
- [ ] Global client instance
- [ ] Tests passing

---

**Continue to next comment for Phases 5-8...**
