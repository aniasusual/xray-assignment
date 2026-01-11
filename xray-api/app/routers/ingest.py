"""
X-Ray API Ingest Router

Handles ingestion of traces from the SDK.

Reference: IMPLEMENTATION_PLAN.md -> "Ingest Endpoint"
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging

from ..database import get_db
from ..schemas import IngestPayload, IngestResponse
from .. import models

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/runs/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_trace(payload: IngestPayload, db: Session = Depends(get_db)):
    """
    Ingest a complete trace (run + steps) from the SDK.

    This is the main endpoint that the SDK sends data to.

    Args:
        payload: Complete run with all steps
        db: Database session (injected)

    Returns:
        Confirmation response with run ID

    Example request:
        POST /api/runs/ingest
        {
            "run": {
                "id": "...",
                "pipeline_name": "competitor_selection",
                "start_time": "2026-01-08T...",
                "status": "success",
                ...
            },
            "steps": [
                {
                    "id": "...",
                    "step_name": "keyword_generation",
                    "step_type": "llm",
                    ...
                },
                ...
            ]
        }
    """
    try:
        # Create Run record
        db_run = models.Run(
            id=payload.run.id,
            pipeline_name=payload.run.pipeline_name,
            pipeline_version=payload.run.pipeline_version,
            start_time=payload.run.start_time,
            end_time=payload.run.end_time,
            status=models.RunStatus(payload.run.status.value),
            run_metadata=payload.run.metadata,  # Note: using run_metadata attribute
            final_output=payload.run.final_output,
        )

        # Add to session
        db.add(db_run)

        # Create Step records
        for step_data in payload.steps:
            db_step = models.Step(
                id=step_data.id,
                run_id=payload.run.id,
                step_name=step_data.step_name,
                step_type=models.StepType(step_data.step_type.value),
                sequence=step_data.sequence,
                start_time=step_data.start_time,
                end_time=step_data.end_time,
                inputs=step_data.inputs,
                outputs=step_data.outputs,
                reasoning=step_data.reasoning,
                candidates_in=step_data.candidates_in,
                candidates_out=step_data.candidates_out,
                candidates_data=step_data.candidates_data,
                filters_applied=step_data.filters_applied,
                step_metadata=step_data.metadata,  # Note: using step_metadata attribute
            )
            db.add(db_step)

        # Commit transaction
        db.commit()

        logger.info(f"✅ Ingested trace for run {payload.run.id} ({payload.run.pipeline_name}) with {len(payload.steps)} steps")

        return IngestResponse(
            success=True,
            run_id=payload.run.id,
            message="Trace ingested successfully",
            steps_count=len(payload.steps),
        )

    except Exception as e:
        db.rollback()
        logger.error(f"❌ Failed to ingest trace: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest trace: {str(e)}"
        )
