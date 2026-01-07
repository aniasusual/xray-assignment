"""
Quick manual test to verify our Pydantic models work correctly.
This demonstrates how the models will be used in practice.

Run with: cd xray-sdk && poetry run python test_models_manual.py
"""

from datetime import datetime, timedelta
from xray.models import RunModel, StepModel, StepType, RunStatus, IngestPayload


def test_step_model():
    """Test creating and using a StepModel"""
    print("=" * 60)
    print("TEST 1: Creating a StepModel")
    print("=" * 60)

    # Create a step (like keyword generation in competitor selection)
    step = StepModel(
        step_name="keyword_generation",
        step_type=StepType.LLM,
        sequence=0,
        inputs={"product_title": "iPhone 15 Pro Case"},
        outputs={"keywords": ["phone", "case", "protective", "iPhone"]},
        reasoning="Used GPT-4 to extract search keywords from product title",
        metadata={"model": "gpt-4", "temperature": 0.3}
    )

    print(f"✅ Created step: {step.step_name}")
    print(f"   ID: {step.id}")
    print(f"   Type: {step.step_type.value}")
    print(f"   Inputs: {step.inputs}")
    print(f"   Outputs: {step.outputs}")
    print(f"   Reasoning: {step.reasoning}")
    print()

    # Test timing
    start = datetime.utcnow()
    end = start + timedelta(milliseconds=250)
    step.set_timing(start, end)

    print(f"✅ Added timing:")
    print(f"   Duration: {step.duration_ms}ms")
    print()

    # Test candidate tracking
    step.set_candidates(candidates_in=5000, candidates_out=450)

    print(f"✅ Added candidate tracking:")
    print(f"   Candidates in: {step.candidates_in}")
    print(f"   Candidates out: {step.candidates_out}")
    print(f"   Reduction rate: {step.reduction_rate:.1%}")  # Shows as percentage
    print()

    # Test JSON serialization (important for API)
    json_data = step.model_dump()
    print(f"✅ Can serialize to JSON: {len(json_data)} fields")
    print()


def test_run_model():
    """Test creating and using a RunModel"""
    print("=" * 60)
    print("TEST 2: Creating a RunModel")
    print("=" * 60)

    # Create a run for competitor selection pipeline
    run = RunModel(
        pipeline_name="competitor_selection",
        pipeline_version="1.0.0",
        metadata={
            "user_id": "user_123",
            "product_category": "phone_cases",
            "environment": "production"
        }
    )

    print(f"✅ Created run: {run.pipeline_name}")
    print(f"   ID: {run.id}")
    print(f"   Status: {run.status.value}")
    print(f"   Started: {run.start_time}")
    print(f"   Metadata: {run.metadata}")
    print()

    # Mark as complete
    run.mark_complete(
        status=RunStatus.SUCCESS,
        final_output={
            "selected_product": {
                "id": "B09X7K3Q2J",
                "name": "Spigen Tough Armor Case",
                "price": 15.99
            }
        }
    )

    print(f"✅ Marked complete:")
    print(f"   Status: {run.status.value}")
    print(f"   Duration: {run.duration_ms:.2f}ms")
    print(f"   Result: {run.final_output}")
    print()


def test_ingest_payload():
    """Test creating a complete payload for API submission"""
    print("=" * 60)
    print("TEST 3: Creating IngestPayload (Run + Steps)")
    print("=" * 60)

    # Create a run
    run = RunModel(
        pipeline_name="fraud_detection",  # Different use case!
        metadata={"transaction_id": "txn_456"}
    )

    # Create multiple steps
    step1 = StepModel(
        step_name="feature_extraction",
        step_type=StepType.TRANSFORM,
        sequence=0,
        inputs={"transaction": {"amount": 1000, "location": "US"}},
        outputs={"features": [0.5, 0.2, 0.8]},
        reasoning="Extracted numerical features from transaction"
    )

    step2 = StepModel(
        step_name="model_inference",
        step_type=StepType.CUSTOM,
        sequence=1,
        inputs={"features": [0.5, 0.2, 0.8]},
        outputs={"fraud_score": 0.15, "is_fraud": False},
        reasoning="Used RandomForest model to predict fraud probability",
        metadata={"model_version": "v2.1"}
    )

    # Combine into payload
    payload = IngestPayload(run=run, steps=[step1, step2])

    print(f"✅ Created payload:")
    print(f"   Run: {payload.run.pipeline_name}")
    print(f"   Steps: {len(payload.steps)}")
    print()

    # Show it works for different pipelines
    for i, step in enumerate(payload.steps):
        print(f"   Step {i}: {step.step_name} ({step.step_type.value})")
    print()

    # Test JSON serialization
    json_data = payload.model_dump()
    print(f"✅ Can serialize to JSON:")
    print(f"   Run keys: {list(json_data['run'].keys())}")
    print(f"   Steps count: {len(json_data['steps'])}")
    print()


def test_general_purpose():
    """Demonstrate that models work for ANY pipeline type"""
    print("=" * 60)
    print("TEST 4: General-Purpose - Different Use Cases")
    print("=" * 60)

    # Use Case 1: E-commerce (from assignment)
    ecommerce_step = StepModel(
        step_name="keyword_generation",
        step_type=StepType.LLM,
        inputs={"product": "laptop stand"},
        outputs={"keywords": ["laptop", "stand", "desk"]},
        reasoning="GPT-4 extracted keywords"
    )
    print(f"✅ E-commerce pipeline step: {ecommerce_step.step_name}")

    # Use Case 2: ML Training Pipeline
    ml_step = StepModel(
        step_name="hyperparameter_tuning",
        step_type=StepType.CUSTOM,
        inputs={"param_grid": {"lr": [0.01, 0.1], "depth": [3, 5]}},
        outputs={"best_params": {"lr": 0.1, "depth": 5}},
        reasoning="Grid search found best params with CV score 0.95"
    )
    print(f"✅ ML pipeline step: {ml_step.step_name}")

    # Use Case 3: DevOps Deployment
    devops_step = StepModel(
        step_name="health_check",
        step_type=StepType.CUSTOM,
        inputs={"service": "api-gateway", "endpoint": "/health"},
        outputs={"status": "healthy", "latency_ms": 45},
        reasoning="All health checks passed with p95 latency < 100ms"
    )
    print(f"✅ DevOps pipeline step: {devops_step.step_name}")

    # Use Case 4: Data Processing
    data_step = StepModel(
        step_name="data_validation",
        step_type=StepType.FILTER,
        inputs={"records": 10000},
        outputs={"valid_records": 9500},
        reasoning="Filtered out records with missing required fields",
        candidates_in=10000,
        candidates_out=9500
    )
    print(f"✅ Data pipeline step: {data_step.step_name}")
    print(f"   Reduction rate: {data_step.reduction_rate:.1%}")

    print()
    print("🎉 ALL USE CASES WORK - Models are truly general-purpose!")
    print()


if __name__ == "__main__":
    print("\n")
    print("🔬 X-RAY SDK - Manual Model Tests")
    print("=" * 60)
    print()

    test_step_model()
    test_run_model()
    test_ingest_payload()
    test_general_purpose()

    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. These models are ready to use")
    print("2. They work for ANY pipeline type (not just e-commerce)")
    print("3. Ready to build context managers (Phase 2)")
    print()
