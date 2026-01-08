"""
X-Ray SDK Data Models

This module defines the core data models used throughout the X-Ray SDK.
These models are based on Pydantic, which provides:
- Automatic validation of data types
- JSON serialization/deserialization
- Clear error messages when data is invalid
- Type hints for IDE autocomplete

Reference: IMPLEMENTATION_PLAN.md Section "Core Concepts & Design Patterns" -> "Data Model Design"
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


# =============================================================================
# ENUMS - Define standardized values for status and step types
# =============================================================================

class RunStatus(str, Enum):
    """
    Status of a pipeline run.

    - RUNNING: Run is currently in progress
    - SUCCESS: Run completed successfully
    - FAILURE: Run failed with an error
    - PARTIAL: Run completed but with some steps failing

    Reference: IMPLEMENTATION_PLAN.md -> Data Model Design -> Run entity
    """
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class StepType(str, Enum):
    """
    Standardized step types for queryability across pipelines.

    These types enable cross-pipeline queries like:
    "Show all runs where FILTER steps eliminated >90% of candidates"

    - LLM: Large Language Model calls (GPT, Claude, etc.)
    - SEARCH: Database or API searches (SQL, Elasticsearch, etc.)
    - FILTER: Rule-based filtering (price, rating, category)
    - RANK: Scoring/ranking algorithms
    - SELECT: Final selection logic
    - TRANSFORM: Data transformation steps
    - CUSTOM: User-defined custom step types

    Reference: IMPLEMENTATION_PLAN.md -> Queryability section
    """
    LLM = "llm"
    SEARCH = "search"
    FILTER = "filter"
    RANK = "rank"
    SELECT = "select"
    TRANSFORM = "transform"
    CUSTOM = "custom"


# =============================================================================
# STEP MODEL - Individual stage in a pipeline
# =============================================================================

class StepModel(BaseModel):
    """
    Represents a single step in a multi-step pipeline.

    This is where the "WHY" of X-Ray lives. Each step captures:
    - What data went in (inputs)
    - What data came out (outputs)
    - WHY this decision was made (reasoning)
    - How many candidates were processed (candidates_in/out)
    - What filters were applied

    Example usage:
        step = StepModel(
            step_name="keyword_generation",
            step_type=StepType.LLM,
            inputs={"product": "iPhone 15 Pro"},
            outputs={"keywords": ["phone", "case", "protective"]},
            reasoning="Used GPT-4 to extract search keywords from product title"
        )

    Reference: IMPLEMENTATION_PLAN.md -> Data Model Design -> Step entity
    """

    # Identity fields
    id: UUID = Field(default_factory=uuid4, description="Unique identifier for this step")
    run_id: Optional[UUID] = Field(default=None, description="Foreign key to parent Run")

    # Step identification
    step_name: str = Field(..., description="Human-readable name (e.g., 'keyword_generation')")
    step_type: StepType = Field(..., description="Standardized step type for querying")
    sequence: int = Field(default=0, description="Order in pipeline (0-indexed)")

    # Timing (automatically captured by context manager)
    start_time: Optional[datetime] = Field(default=None, description="When step started")
    end_time: Optional[datetime] = Field(default=None, description="When step ended")

    # Decision context - THE CORE OF X-RAY
    inputs: Dict[str, Any] = Field(default_factory=dict, description="What data went into this step")
    outputs: Dict[str, Any] = Field(default_factory=dict, description="What data came out of this step")
    reasoning: str = Field(default="", description="WHY this decision was made")

    # Candidate tracking (for filtering/selection steps)
    candidates_in: Optional[int] = Field(default=None, description="Number of candidates before this step")
    candidates_out: Optional[int] = Field(default=None, description="Number of candidates after this step")
    candidates_data: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Full or sampled candidate data (controlled by sampling strategy)"
    )

    # Filter details
    filters_applied: Dict[str, Any] = Field(
        default_factory=dict,
        description="Filters used in this step (e.g., {'min_price': 10, 'max_price': 100})"
    )

    # Extensibility - Store any custom data here
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom metadata (e.g., {'model': 'gpt-4', 'temperature': 0.7})"
    )

    # Pydantic configuration
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "run_id": "123e4567-e89b-12d3-a456-426614174000",
                "step_name": "keyword_generation",
                "step_type": "llm",
                "sequence": 0,
                "inputs": {"product": "iPhone 15 Pro Case"},
                "outputs": {"keywords": ["phone", "case", "protective", "iPhone"]},
                "reasoning": "Used GPT-4 with temperature=0.3 to extract search keywords",
                "metadata": {"model": "gpt-4", "temperature": 0.3}
            }
        }
    }

    # Calculated properties
    @property
    def duration_ms(self) -> Optional[float]:
        """
        Calculate step duration in milliseconds.

        Returns None if timing data is incomplete.
        This is useful for performance analysis.

        Example:
            print(f"Step took {step.duration_ms}ms")
        """
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() * 1000
        return None

    @property
    def reduction_rate(self) -> Optional[float]:
        """
        Calculate what percentage of candidates were eliminated.

        Returns value between 0 and 1 (e.g., 0.95 = 95% eliminated).
        Returns None if candidate counts are not set.

        This is crucial for debugging aggressive filters!

        Example:
            if step.reduction_rate and step.reduction_rate > 0.9:
                print("WARNING: This step eliminated >90% of candidates!")

        Reference: IMPLEMENTATION_PLAN.md -> Queryability -> Cross-pipeline queries
        """
        if self.candidates_in and self.candidates_out is not None:
            if self.candidates_in == 0:
                return None
            eliminated = self.candidates_in - self.candidates_out
            return eliminated / self.candidates_in
        return None

    def set_timing(self, start: datetime, end: datetime) -> None:
        """Helper method to set timing in one call."""
        self.start_time = start
        self.end_time = end

    def set_candidates(
        self,
        candidates_in: int,
        candidates_out: int,
        data: Optional[List[Dict[str, Any]]] = None,
        auto_sample: bool = True,
    ) -> None:
        """
        Helper method to set candidate tracking data.

        Args:
            candidates_in: Number of candidates before step
            candidates_out: Number of candidates after step
            data: Optional list of candidate objects (will be sampled if too large)
            auto_sample: If True, automatically apply sampling to large datasets

        Example:
            # Without data
            step.set_candidates(5000, 50)

            # With full data (will be sampled automatically)
            step.set_candidates(5000, 50, data=all_candidates)

            # With data, no sampling (testing only)
            step.set_candidates(5000, 50, data=all_candidates, auto_sample=False)
        """
        self.candidates_in = candidates_in
        self.candidates_out = candidates_out

        # Apply sampling if data provided and auto_sample is True
        if data and auto_sample:
            from .sampling import auto_sample_candidates, should_sample

            if should_sample(data):
                # Store sampled data + metadata about sampling
                self.candidates_data = auto_sample_candidates(data)
                self.metadata["sampling_applied"] = True
                self.metadata["original_data_count"] = len(data)
                self.metadata["sampled_data_count"] = len(self.candidates_data)
            else:
                # Data is small enough, store as-is
                self.candidates_data = data
        else:
            # No sampling requested or no data provided
            self.candidates_data = data


# =============================================================================
# RUN MODEL - Complete pipeline execution
# =============================================================================

class RunModel(BaseModel):
    """
    Represents a complete execution of a multi-step pipeline.

    A Run is the top-level container that holds all Steps.
    Think of it as a "trace" in traditional observability systems,
    but focused on decision-making rather than performance.

    Example usage:
        run = RunModel(
            pipeline_name="competitor_selection",
            pipeline_version="v1.2.0",
            metadata={"user_id": "123", "product_category": "phone_cases"}
        )

    Reference: IMPLEMENTATION_PLAN.md -> Data Model Design -> Run entity
    """

    # Identity
    id: UUID = Field(default_factory=uuid4, description="Unique identifier for this run")

    # Pipeline identification
    pipeline_name: str = Field(..., description="Name of the pipeline (e.g., 'competitor_selection')")
    pipeline_version: str = Field(default="1.0.0", description="Version for tracking changes over time")

    # Timing
    start_time: datetime = Field(default_factory=datetime.utcnow, description="When run started")
    end_time: Optional[datetime] = Field(default=None, description="When run ended")

    # Status
    status: RunStatus = Field(default=RunStatus.RUNNING, description="Current status of the run")

    # Context - Store any custom data about this run
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Custom metadata (e.g., user_id, environment, input parameters)"
    )

    # Final result
    final_output: Optional[Dict[str, Any]] = Field(
        default=None,
        description="The ultimate result of the pipeline"
    )

    # Pydantic configuration
    model_config = {
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "pipeline_name": "competitor_selection",
                "pipeline_version": "1.0.0",
                "status": "success",
                "metadata": {
                    "user_id": "user_123",
                    "product_id": "prod_456",
                    "category": "phone_cases"
                },
                "final_output": {
                    "selected_product": {
                        "id": "B09X7K3Q2J",
                        "name": "Spigen Tough Armor Case",
                        "price": 15.99
                    }
                }
            }
        }
    }

    # Calculated properties
    @property
    def duration_ms(self) -> Optional[float]:
        """
        Calculate total run duration in milliseconds.

        Returns None if run hasn't ended yet.
        """
        if self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() * 1000
        return None

    def mark_complete(self, status: RunStatus, final_output: Optional[Dict[str, Any]] = None) -> None:
        """
        Mark run as complete with final status and output.

        Args:
            status: Final status (SUCCESS, FAILURE, or PARTIAL)
            final_output: Optional final result of the pipeline
        """
        self.end_time = datetime.utcnow()
        self.status = status
        if final_output is not None:
            self.final_output = final_output


# =============================================================================
# INGEST PAYLOAD - Combined Run + Steps for API submission
# =============================================================================

class IngestPayload(BaseModel):
    """
    Combined payload for submitting a complete Run with all its Steps to the API.

    This is what gets sent to POST /api/v1/runs/ingest

    Example usage:
        payload = IngestPayload(
            run=run_model,
            steps=[step1, step2, step3]
        )

        # Send to API
        response = httpx.post("http://api/runs/ingest", json=payload.model_dump())

    Reference: IMPLEMENTATION_PLAN.md -> API Design -> Ingestion Endpoint
    """

    run: RunModel = Field(..., description="The Run metadata")
    steps: List[StepModel] = Field(default_factory=list, description="All steps in this run")

    @field_validator('steps')
    @classmethod
    def validate_steps(cls, steps: List[StepModel], info) -> List[StepModel]:
        """
        Validate that all steps have sequential sequence numbers.

        This helps catch bugs where steps are out of order.
        """
        if steps:
            sequences = [step.sequence for step in steps]
            if sequences != sorted(sequences):
                raise ValueError("Steps must be in sequential order by sequence number")
        return steps

    model_config = {
        "json_schema_extra": {
            "example": {
                "run": {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "pipeline_name": "competitor_selection",
                    "status": "success"
                },
                "steps": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "step_name": "keyword_generation",
                        "step_type": "llm",
                        "sequence": 0
                    },
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440001",
                        "step_name": "search",
                        "step_type": "search",
                        "sequence": 1
                    }
                ]
            }
        }
    }
