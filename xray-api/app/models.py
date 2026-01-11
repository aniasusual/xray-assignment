"""
X-Ray API Database Models (SQLAlchemy)

These are the database table definitions using SQLAlchemy ORM.

Key design decisions:
- Two tables: runs and steps (simple hierarchy)
- JSONB columns for flexible data (inputs, outputs, metadata, etc.)
- Indexes on commonly queried fields (pipeline_name, status, step_type, timestamps)
- Foreign key from steps to runs for relationship

Reference: IMPLEMENTATION_PLAN.md -> "Database Schema"
"""

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index, Enum as SQLEnum, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from .database import Base


# =============================================================================
# ENUMS - Match SDK enums
# =============================================================================


class RunStatus(str, enum.Enum):
    """Run status - matches SDK RunStatus enum"""
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class StepType(str, enum.Enum):
    """Step type - matches SDK StepType enum"""
    LLM = "llm"
    SEARCH = "search"
    FILTER = "filter"
    RANK = "rank"
    SELECT = "select"
    TRANSFORM = "transform"
    CUSTOM = "custom"


# =============================================================================
# MODELS - Database tables
# =============================================================================


class Run(Base):
    """
    Run table - stores complete pipeline executions.

    This corresponds to the SDK's RunModel.
    Each row represents one execution of a pipeline.
    """
    __tablename__ = "runs"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)

    # Pipeline identification
    pipeline_name = Column(String, nullable=False, index=True)
    pipeline_version = Column(String, default="1.0.0")

    # Timing
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)

    # Status
    status = Column(SQLEnum(RunStatus), nullable=False, default=RunStatus.RUNNING, index=True)

    # Flexible data stored as JSONB
    run_metadata = Column("metadata", JSONB, default={})  # Column name is "metadata", Python attribute is "run_metadata"
    final_output = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to steps
    steps = relationship("Step", back_populates="run", cascade="all, delete-orphan")

    # Indexes for common queries
    __table_args__ = (
        Index("idx_run_pipeline_status", "pipeline_name", "status"),
        Index("idx_run_start_time", "start_time"),
    )


class Step(Base):
    """
    Step table - stores individual steps within runs.

    This corresponds to the SDK's StepModel.
    Each row represents one step in a pipeline execution.
    """
    __tablename__ = "steps"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, index=True)

    # Foreign key to run
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)

    # Step identification
    step_name = Column(String, nullable=False, index=True)
    step_type = Column(SQLEnum(StepType), nullable=False, index=True)
    sequence = Column(Integer, default=0)

    # Timing
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)

    # Flexible data stored as JSONB
    inputs = Column(JSONB, default={})
    outputs = Column(JSONB, default={})
    reasoning = Column(String, default="")

    # Candidate tracking
    candidates_in = Column(Integer, nullable=True, index=True)
    candidates_out = Column(Integer, nullable=True, index=True)
    candidates_data = Column(JSONB, nullable=True)  # Sampled candidate data

    # Filter tracking
    filters_applied = Column(JSONB, default={})

    # Extensible metadata
    step_metadata = Column("metadata", JSONB, default={})  # Column name is "metadata", Python attribute is "step_metadata"

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship to run
    run = relationship("Run", back_populates="steps")

    # Indexes for common queries
    __table_args__ = (
        Index("idx_step_run_sequence", "run_id", "sequence"),
        Index("idx_step_type", "step_type"),
        Index("idx_step_name", "step_name"),
        Index("idx_step_candidates", "candidates_in", "candidates_out"),
    )
