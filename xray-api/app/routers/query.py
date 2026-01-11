"""
X-Ray API Query Router

Handles querying and analyzing traces.

This is where the debugging power comes from!

Reference: IMPLEMENTATION_PLAN.md -> "Query Endpoints"
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from typing import Optional, List
import logging

from ..database import get_db
from ..schemas import (
    RunSchema,
    StepSchema,
    RunDetailResponse,
    RunListResponse,
    StepListResponse,
    StepQueryFilter,
    AnalyticsResponse,
)
from .. import models
from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# RUN QUERIES
# =============================================================================


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
async def get_run_by_id(run_id: str, db: Session = Depends(get_db)):
    """
    Get a specific run with all its steps.

    This is used for detailed debugging of a specific run.

    Args:
        run_id: UUID of the run
        db: Database session

    Returns:
        Complete run with all steps

    Example:
        GET /api/runs/abc-123
    """
    # Query run
    db_run = db.query(models.Run).filter(models.Run.id == run_id).first()

    if not db_run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run {run_id} not found"
        )

    # Query steps (ordered by sequence)
    db_steps = db.query(models.Step)\
        .filter(models.Step.run_id == run_id)\
        .order_by(models.Step.sequence)\
        .all()

    return RunDetailResponse(
        run=RunSchema.model_validate(db_run),
        steps=[StepSchema.model_validate(step) for step in db_steps]
    )


@router.get("/runs", response_model=RunListResponse)
async def list_runs(
    pipeline_name: Optional[str] = Query(None, description="Filter by pipeline name"),
    status: Optional[str] = Query(None, description="Filter by status (running, success, failure)"),
    limit: int = Query(50, ge=1, le=settings.max_page_size, description="Number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db)
):
    """
    List runs with optional filtering.

    Supports pagination and basic filtering.

    Args:
        pipeline_name: Filter by pipeline name
        status: Filter by status
        limit: Page size
        offset: Page offset
        db: Database session

    Returns:
        Paginated list of runs

    Example:
        GET /api/runs?pipeline_name=competitor_selection&status=success&limit=20
    """
    # Build query
    query = db.query(models.Run)

    # Apply filters
    if pipeline_name:
        query = query.filter(models.Run.pipeline_name == pipeline_name)

    if status:
        try:
            status_enum = models.RunStatus(status)
            query = query.filter(models.Run.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status}"
            )

    # Get total count
    total = query.count()

    # Apply pagination and ordering
    runs = query.order_by(models.Run.start_time.desc())\
        .limit(limit)\
        .offset(offset)\
        .all()

    return RunListResponse(
        runs=[RunSchema.model_validate(run) for run in runs],
        total=total,
        page=offset // limit + 1,
        page_size=limit
    )


# =============================================================================
# STEP QUERIES (Cross-Pipeline)
# =============================================================================


@router.post("/steps/query", response_model=StepListResponse)
async def query_steps(
    filter_params: StepQueryFilter,
    limit: int = Query(50, ge=1, le=settings.max_page_size),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Query steps across all pipelines.

    This is the powerful cross-pipeline query endpoint!

    Examples:
    - "Show me all LLM steps"
    - "Show me all FILTER steps that eliminated >90% candidates"
    - "Show me all steps in the competitor_selection pipeline"

    Args:
        filter_params: Query filters
        limit: Page size
        offset: Page offset
        db: Database session

    Returns:
        Matching steps

    Example request:
        POST /api/steps/query
        {
            "step_type": "filter",
            "min_reduction_rate": 0.9
        }
    """
    # Build query
    query = db.query(models.Step)

    # Apply filters
    if filter_params.step_type:
        query = query.filter(models.Step.step_type == models.StepType(filter_params.step_type.value))

    if filter_params.step_name:
        query = query.filter(models.Step.step_name == filter_params.step_name)

    if filter_params.pipeline_name:
        # Join with runs table
        query = query.join(models.Run).filter(models.Run.pipeline_name == filter_params.pipeline_name)

    # Candidate filtering
    if filter_params.min_candidates_in is not None:
        query = query.filter(models.Step.candidates_in >= filter_params.min_candidates_in)

    if filter_params.max_candidates_in is not None:
        query = query.filter(models.Step.candidates_in <= filter_params.max_candidates_in)

    if filter_params.min_candidates_out is not None:
        query = query.filter(models.Step.candidates_out >= filter_params.min_candidates_out)

    if filter_params.max_candidates_out is not None:
        query = query.filter(models.Step.candidates_out <= filter_params.max_candidates_out)

    # Reduction rate filtering (requires calculation)
    if filter_params.min_reduction_rate is not None or filter_params.max_reduction_rate is not None:
        # Calculate reduction rate: (candidates_in - candidates_out) / candidates_in
        # Only consider steps with candidates_in > 0
        query = query.filter(models.Step.candidates_in > 0)

        if filter_params.min_reduction_rate is not None:
            # (candidates_in - candidates_out) / candidates_in >= min_rate
            # candidates_in - candidates_out >= min_rate * candidates_in
            # candidates_out <= candidates_in * (1 - min_rate)
            query = query.filter(
                models.Step.candidates_out <= models.Step.candidates_in * (1 - filter_params.min_reduction_rate)
            )

        if filter_params.max_reduction_rate is not None:
            query = query.filter(
                models.Step.candidates_out >= models.Step.candidates_in * (1 - filter_params.max_reduction_rate)
            )

    # Time range filtering
    if filter_params.start_time_from:
        query = query.filter(models.Step.start_time >= filter_params.start_time_from)

    if filter_params.start_time_to:
        query = query.filter(models.Step.start_time <= filter_params.start_time_to)

    # Get total count
    total = query.count()

    # Apply pagination
    steps = query.order_by(models.Step.start_time.desc())\
        .limit(limit)\
        .offset(offset)\
        .all()

    return StepListResponse(
        steps=[StepSchema.model_validate(step) for step in steps],
        total=total,
        page=offset // limit + 1,
        page_size=limit
    )


# =============================================================================
# ANALYTICS
# =============================================================================


@router.get("/analytics/pipeline/{pipeline_name}", response_model=AnalyticsResponse)
async def get_pipeline_analytics(pipeline_name: str, db: Session = Depends(get_db)):
    """
    Get analytics/statistics for a specific pipeline.

    Provides aggregated metrics:
    - Total runs
    - Success/failure rate
    - Average duration
    - Step-level statistics

    Args:
        pipeline_name: Name of the pipeline
        db: Database session

    Returns:
        Aggregated analytics

    Example:
        GET /api/analytics/pipeline/competitor_selection
    """
    # Query runs for this pipeline
    runs = db.query(models.Run).filter(models.Run.pipeline_name == pipeline_name).all()

    if not runs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No runs found for pipeline: {pipeline_name}"
        )

    # Calculate statistics
    total_runs = len(runs)
    success_count = sum(1 for r in runs if r.status == models.RunStatus.SUCCESS)
    failure_count = sum(1 for r in runs if r.status == models.RunStatus.FAILURE)
    success_rate = success_count / total_runs if total_runs > 0 else 0

    # Calculate average duration (only for completed runs)
    durations = []
    for run in runs:
        if run.start_time and run.end_time:
            duration_ms = (run.end_time - run.start_time).total_seconds() * 1000
            durations.append(duration_ms)

    avg_duration_ms = sum(durations) / len(durations) if durations else None

    # Get step-level statistics
    run_ids = [r.id for r in runs]
    steps = db.query(models.Step).filter(models.Step.run_id.in_(run_ids)).all()

    total_steps = len(steps)

    # Count steps by type
    steps_by_type = {}
    for step in steps:
        step_type = step.step_type.value
        steps_by_type[step_type] = steps_by_type.get(step_type, 0) + 1

    return AnalyticsResponse(
        pipeline_name=pipeline_name,
        total_runs=total_runs,
        success_count=success_count,
        failure_count=failure_count,
        success_rate=success_rate,
        avg_duration_ms=avg_duration_ms,
        total_steps=total_steps,
        steps_by_type=steps_by_type,
    )
