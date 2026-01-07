"""
X-Ray SDK Context Management

This module implements the context manager pattern for tracking runs and steps.
Uses Python's contextvars for thread-safe, async-compatible context storage.

Key concepts:
- RunContext: Manages a complete pipeline execution
- StepContext: Manages individual steps within a run
- contextvars: Thread-safe storage (works with async code too!)

Reference: IMPLEMENTATION_PLAN.md -> "Context Manager Pattern"
"""

from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from .models import RunModel, RunStatus, StepModel, StepType


# =============================================================================
# CONTEXT VARIABLES - Thread-safe storage for current run/step
# =============================================================================

# These store the "current" run and step in a thread-safe way
# Even in async code or multi-threaded environments, each context is isolated
_current_run_context: ContextVar[Optional["RunContext"]] = ContextVar(
    "current_run_context", default=None
)
_current_step_context: ContextVar[Optional["StepContext"]] = ContextVar(
    "current_step_context", default=None
)


# =============================================================================
# HELPER FUNCTIONS - Access current contexts
# =============================================================================


def get_current_run() -> Optional["RunContext"]:
    """
    Get the currently active RunContext.

    Returns None if no run is active.

    Example:
        if run := get_current_run():
            print(f"Currently in run: {run.run_model.pipeline_name}")
    """
    return _current_run_context.get()


def get_current_step() -> Optional["StepContext"]:
    """
    Get the currently active StepContext.

    Returns None if no step is active.

    Example:
        if step := get_current_step():
            step.set_reasoning("Updated reasoning from nested function")
    """
    return _current_step_context.get()


# =============================================================================
# RUN CONTEXT - Manages a complete pipeline execution
# =============================================================================


class RunContext:
    """
    Context manager for a complete pipeline run.

    Usage:
        with RunContext("competitor_selection") as run:
            # Your pipeline code here
            with run.step("keyword_generation", StepType.LLM) as step:
                result = do_work()
                step.set_output(result)

    Features:
    - Automatically tracks start/end time
    - Manages run status (running → success/failure)
    - Collects all steps in the run
    - Thread-safe (uses contextvars)

    Reference: IMPLEMENTATION_PLAN.md -> "SDK Design Pattern: Context Manager"
    """

    def __init__(
        self,
        pipeline_name: str,
        pipeline_version: str = "1.0.0",
        metadata: Optional[Dict[str, Any]] = None,
        auto_send: bool = True,
    ):
        """
        Initialize a new run context.

        Args:
            pipeline_name: Name of the pipeline (e.g., "competitor_selection")
            pipeline_version: Version string for tracking changes
            metadata: Additional context (user_id, environment, etc.)
            auto_send: If True, automatically send to API when run completes
        """
        self.run_model = RunModel(
            pipeline_name=pipeline_name,
            pipeline_version=pipeline_version,
            metadata=metadata or {},
        )
        self.steps: List[StepModel] = []
        self.auto_send = auto_send
        self._sequence_counter = 0  # Track step order
        self._previous_run_context: Optional[RunContext] = None

    def __enter__(self) -> "RunContext":
        """
        Enter the context manager - called when entering 'with' block.

        This:
        1. Records the start time (already set in RunModel.__init__)
        2. Sets this as the current run context
        3. Returns self so user can access methods

        Reference: Python Context Manager Protocol
        """
        # Store the previous run context (in case of nested runs)
        self._previous_run_context = _current_run_context.get()

        # Set this as the current run
        _current_run_context.set(self)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the context manager - called when leaving 'with' block.

        This:
        1. Records the end time
        2. Sets the final status based on whether an exception occurred
        3. Optionally sends data to API
        4. Restores previous run context

        Args:
            exc_type: Exception type if an error occurred, None otherwise
            exc_val: Exception value
            exc_tb: Exception traceback

        Returns:
            False (don't suppress exceptions)

        Reference: Python Context Manager Protocol
        """
        # Determine final status
        if exc_type is None:
            # No exception - success!
            status = RunStatus.SUCCESS
        else:
            # Exception occurred - failure
            status = RunStatus.FAILURE

        # Mark run as complete
        self.run_model.mark_complete(status=status)

        # Phase 5: Send to API if auto_send is True
        if self.auto_send:
            from .client import send_trace
            from .models import IngestPayload

            # Create payload with run and all collected steps
            payload = IngestPayload(run=self.run_model, steps=self.steps)

            # Send to API (respects async_mode and fallback_mode from config)
            send_trace(payload)

        # Restore previous run context
        _current_run_context.set(self._previous_run_context)

        # Don't suppress exceptions - let them propagate
        return False

    def step(
        self,
        step_name: str,
        step_type: StepType = StepType.CUSTOM,
    ) -> "StepContext":
        """
        Create a new step within this run.

        Args:
            step_name: Human-readable name (e.g., "keyword_generation")
            step_type: Standardized step type for queryability

        Returns:
            StepContext that can be used as a context manager

        Example:
            with run.step("filter_candidates", StepType.FILTER) as step:
                filtered = [c for c in candidates if c.price < 100]
                step.set_candidates(len(candidates), len(filtered))
                step.set_reasoning(f"Filtered by price < 100")
        """
        # Create a new step with the current sequence number
        step_context = StepContext(
            run_context=self,
            step_name=step_name,
            step_type=step_type,
            sequence=self._sequence_counter,
        )

        # Increment sequence counter for next step
        self._sequence_counter += 1

        return step_context

    def add_step(self, step_model: StepModel) -> None:
        """
        Add a completed step to this run.

        This is called automatically by StepContext.__exit__
        Users don't need to call this directly.

        Args:
            step_model: The completed step to add
        """
        # Link step to this run
        step_model.run_id = self.run_model.id

        # Add to our list
        self.steps.append(step_model)

    def set_metadata(self, key: str, value: Any) -> None:
        """
        Add metadata to the run.

        Example:
            run.set_metadata("user_id", "user_123")
            run.set_metadata("environment", "production")
        """
        self.run_model.metadata[key] = value

    def set_final_output(self, output: Dict[str, Any]) -> None:
        """
        Set the final output of the pipeline.

        Example:
            run.set_final_output({
                "selected_product": product,
                "confidence": 0.95
            })
        """
        self.run_model.final_output = output


# =============================================================================
# STEP CONTEXT - Manages individual steps within a run
# =============================================================================


class StepContext:
    """
    Context manager for an individual step in a pipeline.

    Usage:
        with run.step("keyword_generation", StepType.LLM) as step:
            keywords = generate_keywords(product)
            step.set_inputs({"product": product})
            step.set_outputs({"keywords": keywords})
            step.set_reasoning("Used GPT-4 to extract keywords")

    Features:
    - Automatically tracks start/end time (precision timing!)
    - Provides convenient methods for setting data
    - Handles exceptions gracefully
    - Thread-safe

    Reference: IMPLEMENTATION_PLAN.md -> "SDK Design Pattern: Context Manager"
    """

    def __init__(
        self,
        run_context: RunContext,
        step_name: str,
        step_type: StepType,
        sequence: int,
    ):
        """
        Initialize a new step context.

        Args:
            run_context: Parent run this step belongs to
            step_name: Human-readable name
            step_type: Standardized type for querying
            sequence: Order in the pipeline (0-indexed)
        """
        self.run_context = run_context
        self.step_model = StepModel(
            step_name=step_name,
            step_type=step_type,
            sequence=sequence,
        )
        self._previous_step_context: Optional[StepContext] = None

    def __enter__(self) -> "StepContext":
        """
        Enter the step context - records start time.

        Returns self so user can call methods like set_inputs(), set_reasoning(), etc.
        """
        # Record start time
        self.step_model.start_time = datetime.utcnow()

        # Store previous step context (for nested steps, though rare)
        self._previous_step_context = _current_step_context.get()

        # Set as current step
        _current_step_context.set(self)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the step context - records end time and adds to run.

        If an exception occurred, it will be noted in metadata.
        """
        # Record end time
        self.step_model.end_time = datetime.utcnow()

        # If an exception occurred, note it
        if exc_type is not None:
            self.step_model.metadata["exception"] = {
                "type": exc_type.__name__,
                "message": str(exc_val),
            }

        # Add this step to the parent run
        self.run_context.add_step(self.step_model)

        # Restore previous step context
        _current_step_context.set(self._previous_step_context)

        # Don't suppress exceptions
        return False

    # =========================================================================
    # CONVENIENCE METHODS - Make it easy to set data
    # =========================================================================

    def set_inputs(self, inputs: Dict[str, Any]) -> None:
        """
        Set the inputs for this step.

        Args:
            inputs: Dictionary of input data

        Example:
            step.set_inputs({"product_title": "iPhone 15 Pro", "category": "electronics"})
        """
        self.step_model.inputs = inputs

    def set_outputs(self, outputs: Dict[str, Any]) -> None:
        """
        Set the outputs for this step.

        Args:
            outputs: Dictionary of output data

        Example:
            step.set_outputs({"keywords": ["phone", "case", "protective"]})
        """
        self.step_model.outputs = outputs

    def set_reasoning(self, reasoning: str) -> None:
        """
        Set the reasoning for WHY this decision was made.

        This is THE MOST IMPORTANT part of X-Ray!
        Explain WHY, not just WHAT.

        Args:
            reasoning: Human-readable explanation

        Example:
            step.set_reasoning(
                "Used GPT-4 with temperature=0.3 to extract search keywords. "
                "Selected these terms because they match the product category."
            )
        """
        self.step_model.reasoning = reasoning

    def set_candidates(
        self,
        candidates_in: int,
        candidates_out: int,
        data: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """
        Set candidate tracking data (for filtering/selection steps).

        Args:
            candidates_in: Number before this step
            candidates_out: Number after this step
            data: Optional list of candidate objects (will be sampled later)

        Example:
            step.set_candidates(
                candidates_in=5000,
                candidates_out=450,
                data=sampled_candidates  # Optional
            )

            # Later, can query: step.reduction_rate → 0.91 (91% eliminated!)
        """
        self.step_model.set_candidates(candidates_in, candidates_out, data)

    def set_filters(self, filters: Dict[str, Any]) -> None:
        """
        Set the filters applied in this step.

        Args:
            filters: Dictionary describing filter rules

        Example:
            step.set_filters({
                "min_price": 10.00,
                "max_price": 100.00,
                "min_rating": 4.0,
                "category": "phone_cases"
            })
        """
        self.step_model.filters_applied = filters

    def add_metadata(self, key: str, value: Any) -> None:
        """
        Add custom metadata to this step.

        Args:
            key: Metadata key
            value: Metadata value (any JSON-serializable type)

        Example:
            step.add_metadata("model", "gpt-4")
            step.add_metadata("temperature", 0.7)
            step.add_metadata("tokens_used", 1234)
        """
        self.step_model.metadata[key] = value

    def update_metadata(self, metadata: Dict[str, Any]) -> None:
        """
        Update multiple metadata fields at once.

        Args:
            metadata: Dictionary of metadata to add

        Example:
            step.update_metadata({
                "model": "gpt-4",
                "temperature": 0.7,
                "max_tokens": 1000
            })
        """
        self.step_model.metadata.update(metadata)
