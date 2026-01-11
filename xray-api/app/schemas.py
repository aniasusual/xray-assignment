"""
X-Ray API Pydantic Schemas

These are the request/response schemas for the API.
They match the SDK models but are used for API validation and serialization.

Reference: IMPLEMENTATION_PLAN.md -> "API Schemas"
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
import enum


# =============================================================================
# ENUMS - Match SDK and database enums
# =============================================================================


class RunStatus(str, enum.Enum):
    """Run status"""
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class StepType(str, enum.Enum):
    """Step type"""
    LLM = "llm"
    SEARCH = "search"
    FILTER = "filter"
    RANK = "rank"
    SELECT = "select"
    TRANSFORM = "transform"
    CUSTOM = "custom"


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================


class StepSchema(BaseModel):
    """
    Step schema - matches SDK StepModel.

    Used for both ingest (request) and query (response).
    """
    id: UUID
    run_id: Optional[UUID] = None
    step_name: str
    step_type: StepType
    sequence: int = 0

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""

    candidates_in: Optional[int] = None
    candidates_out: Optional[int] = None
    candidates_data: Optional[List[Dict[str, Any]]] = None

    filters_applied: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict, validation_alias="step_metadata")

    class Config:
        from_attributes = True  # Allow converting from SQLAlchemy models
        populate_by_name = True  # Allow both 'metadata' and 'step_metadata'


class RunSchema(BaseModel):
    """
    Run schema - matches SDK RunModel.

    Used for both ingest (request) and query (response).
    """
    id: UUID
    pipeline_name: str
    pipeline_version: str = "1.0.0"

    start_time: datetime
    end_time: Optional[datetime] = None

    status: RunStatus = RunStatus.RUNNING

    metadata: Dict[str, Any] = Field(default_factory=dict, validation_alias="run_metadata")
    final_output: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
        populate_by_name = True  # Allow both 'metadata' and 'run_metadata'


class IngestPayload(BaseModel):
    """
    Ingest payload - what the SDK sends to the API.

    Contains a complete run with all its steps.
    """
    run: RunSchema
    steps: List[StepSchema] = Field(default_factory=list)


class IngestResponse(BaseModel):
    """
    Response from ingest endpoint.

    Confirms receipt and provides the run ID.
    """
    success: bool
    run_id: UUID
    message: str = "Trace ingested successfully"
    steps_count: int


class RunDetailResponse(BaseModel):
    """
    Detailed run response - includes all steps.

    Used when querying a specific run by ID.
    """
    run: RunSchema
    steps: List[StepSchema]


class RunListResponse(BaseModel):
    """
    Paginated list of runs (without steps).

    Used for listing/searching runs.
    """
    runs: List[RunSchema]
    total: int
    page: int
    page_size: int


class QueryFilter(BaseModel):
    """
    Query filter for searching runs.

    Allows filtering by various criteria.
    """
    pipeline_name: Optional[str] = None
    pipeline_version: Optional[str] = None
    status: Optional[RunStatus] = None
    start_time_from: Optional[datetime] = None
    start_time_to: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class StepQueryFilter(BaseModel):
    """
    Query filter for searching steps across pipelines.

    This enables cross-pipeline queries like:
    - "Show me all LLM steps"
    - "Show me all FILTER steps that eliminated >90% candidates"
    """
    step_type: Optional[StepType] = None
    step_name: Optional[str] = None
    pipeline_name: Optional[str] = None

    # Candidate filtering
    min_candidates_in: Optional[int] = None
    max_candidates_in: Optional[int] = None
    min_candidates_out: Optional[int] = None
    max_candidates_out: Optional[int] = None

    # Reduction rate filtering (e.g., >90% elimination)
    min_reduction_rate: Optional[float] = Field(None, ge=0, le=1)
    max_reduction_rate: Optional[float] = Field(None, ge=0, le=1)

    # Time range
    start_time_from: Optional[datetime] = None
    start_time_to: Optional[datetime] = None


class StepListResponse(BaseModel):
    """
    Paginated list of steps.

    Used for cross-pipeline step queries.
    """
    steps: List[StepSchema]
    total: int
    page: int
    page_size: int


class AnalyticsResponse(BaseModel):
    """
    Analytics/statistics for a pipeline.

    Aggregated metrics for understanding pipeline performance.
    """
    pipeline_name: str
    total_runs: int
    success_count: int
    failure_count: int
    success_rate: float
    avg_duration_ms: Optional[float]

    # Step-level stats
    total_steps: int
    steps_by_type: Dict[str, int]

    # Optional: most common failure points
    bottleneck_steps: Optional[List[Dict[str, Any]]] = None
