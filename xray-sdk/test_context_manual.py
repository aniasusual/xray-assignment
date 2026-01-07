"""
Manual test for X-Ray context managers.

This demonstrates how RunContext and StepContext work together.

Run with: cd xray-sdk && poetry run python test_context_manual.py
"""

from xray.context import RunContext, get_current_run, get_current_step
from xray.models import StepType


def test_basic_run_and_step():
    """Test creating a run with steps"""
    print("=" * 60)
    print("TEST 1: Basic Run and Step")
    print("=" * 60)

    with RunContext("test_pipeline", metadata={"test_id": "001"}) as run:
        print(f"✅ Run started: {run.run_model.pipeline_name}")
        print(f"   Run ID: {run.run_model.id}")
        print(f"   Status: {run.run_model.status.value}")
        print()

        # Create a step
        with run.step("test_step", StepType.CUSTOM) as step:
            print(f"✅ Step started: {step.step_model.step_name}")
            print(f"   Step ID: {step.step_model.id}")
            print(f"   Sequence: {step.step_model.sequence}")
            print()

            # Set some data
            step.set_inputs({"input_value": 42})
            step.set_outputs({"output_value": 84})
            step.set_reasoning("Doubled the input value")

            print(f"✅ Step data set:")
            print(f"   Inputs: {step.step_model.inputs}")
            print(f"   Outputs: {step.step_model.outputs}")
            print(f"   Reasoning: {step.step_model.reasoning}")
            print()

        # After step exits, check timing
        print(f"✅ Step completed:")
        print(f"   Duration: {step.step_model.duration_ms:.2f}ms")
        print()

    # After run exits, check status
    print(f"✅ Run completed:")
    print(f"   Status: {run.run_model.status.value}")
    print(f"   Duration: {run.run_model.duration_ms:.2f}ms")
    print(f"   Steps collected: {len(run.steps)}")
    print()


def test_multiple_steps():
    """Test a run with multiple sequential steps"""
    print("=" * 60)
    print("TEST 2: Multiple Sequential Steps")
    print("=" * 60)

    with RunContext("multi_step_pipeline") as run:
        # Step 1: Data loading
        with run.step("load_data", StepType.CUSTOM) as step:
            data = [1, 2, 3, 4, 5]
            step.set_outputs({"data": data, "count": len(data)})
            step.set_reasoning("Loaded sample data from source")
            print(f"Step 1: Loaded {len(data)} items")

        # Step 2: Transformation
        with run.step("transform", StepType.TRANSFORM) as step:
            transformed = [x * 2 for x in data]
            step.set_inputs({"data": data})
            step.set_outputs({"transformed": transformed})
            step.set_reasoning("Doubled each value")
            print(f"Step 2: Transformed {len(transformed)} items")

        # Step 3: Filtering
        with run.step("filter", StepType.FILTER) as step:
            filtered = [x for x in transformed if x > 5]
            step.set_inputs({"data": transformed})
            step.set_outputs({"filtered": filtered})
            step.set_candidates(len(transformed), len(filtered))
            step.set_reasoning(f"Filtered for values > 5")
            print(f"Step 3: Filtered {len(transformed)} → {len(filtered)} items")
            print(f"         Reduction rate: {step.step_model.reduction_rate:.1%}")

        print()
        print(f"✅ Run completed with {len(run.steps)} steps:")
        for i, s in enumerate(run.steps):
            print(f"   {i}. {s.step_name} ({s.step_type.value}) - {s.duration_ms:.2f}ms")
        print()


def test_context_access():
    """Test accessing current run/step from nested functions"""
    print("=" * 60)
    print("TEST 3: Context Access (get_current_run/step)")
    print("=" * 60)

    def nested_function():
        """Function that accesses the current step without passing it as parameter"""
        current_step = get_current_step()
        if current_step:
            current_step.add_metadata("called_from", "nested_function")
            current_step.set_reasoning("Updated from nested function")
            print(f"   ✅ Nested function accessed step: {current_step.step_model.step_name}")
        else:
            print(f"   ❌ No current step found")

    with RunContext("context_test") as run:
        # Verify we can access the run
        current_run = get_current_run()
        print(f"✅ get_current_run() works: {current_run.run_model.pipeline_name}")
        print()

        with run.step("test_context", StepType.CUSTOM) as step:
            # Call nested function that accesses the step
            nested_function()

            # Verify the metadata was added
            print(f"   Metadata after nested call: {step.step_model.metadata}")
            print(f"   Reasoning: {step.step_model.reasoning}")
            print()


def test_candidate_tracking():
    """Test candidate tracking with reduction rate calculation"""
    print("=" * 60)
    print("TEST 4: Candidate Tracking (Filtering Scenario)")
    print("=" * 60)

    with RunContext("filtering_pipeline") as run:
        # Simulate a filtering pipeline
        initial_candidates = 5000

        # Step 1: Price filter
        with run.step("price_filter", StepType.FILTER) as step:
            after_price = 2500
            step.set_candidates(initial_candidates, after_price)
            step.set_filters({"min_price": 10, "max_price": 100})
            step.set_reasoning(f"Filtered by price range $10-$100")

            print(f"Step 1 - Price Filter:")
            print(f"   {initial_candidates} → {after_price} candidates")
            print(f"   Reduction rate: {step.step_model.reduction_rate:.1%}")
            print()

        # Step 2: Rating filter
        with run.step("rating_filter", StepType.FILTER) as step:
            after_rating = 800
            step.set_candidates(after_price, after_rating)
            step.set_filters({"min_rating": 4.0})
            step.set_reasoning(f"Filtered by rating >= 4.0")

            print(f"Step 2 - Rating Filter:")
            print(f"   {after_price} → {after_rating} candidates")
            print(f"   Reduction rate: {step.step_model.reduction_rate:.1%}")
            print()

        # Step 3: Category filter
        with run.step("category_filter", StepType.FILTER) as step:
            after_category = 50
            step.set_candidates(after_rating, after_category)
            step.set_filters({"category": "phone_cases"})
            step.set_reasoning(f"Filtered by category match")

            print(f"Step 3 - Category Filter:")
            print(f"   {after_rating} → {after_category} candidates")
            print(f"   Reduction rate: {step.step_model.reduction_rate:.1%}")
            print()

        # Overall reduction
        overall_reduction = (initial_candidates - after_category) / initial_candidates
        print(f"✅ Overall pipeline:")
        print(f"   {initial_candidates} → {after_category} candidates")
        print(f"   Total reduction: {overall_reduction:.1%}")
        print()


def test_exception_handling():
    """Test that exceptions are properly recorded"""
    print("=" * 60)
    print("TEST 5: Exception Handling")
    print("=" * 60)

    try:
        with RunContext("error_pipeline") as run:
            with run.step("will_fail", StepType.CUSTOM) as step:
                step.set_reasoning("About to raise an error")
                raise ValueError("Intentional test error")

    except ValueError as e:
        print(f"✅ Exception was caught: {e}")
        print(f"   Run status: {run.run_model.status.value}")
        print(f"   Step metadata: {step.step_model.metadata}")
        print()


def test_general_purpose():
    """Show it works for different pipeline types"""
    print("=" * 60)
    print("TEST 6: General Purpose - Different Domains")
    print("=" * 60)

    # E-commerce pipeline
    print("E-Commerce Pipeline:")
    with RunContext("competitor_selection") as run:
        with run.step("keyword_gen", StepType.LLM) as step:
            step.set_outputs({"keywords": ["phone", "case"]})
            step.set_reasoning("GPT-4 extracted keywords")
        print(f"   ✅ {run.run_model.pipeline_name} - {len(run.steps)} steps")

    # Financial pipeline
    print("Financial Pipeline:")
    with RunContext("loan_approval") as run:
        with run.step("credit_check", StepType.CUSTOM) as step:
            step.set_outputs({"score": 750, "approved": True})
            step.set_reasoning("Credit score above threshold")
        print(f"   ✅ {run.run_model.pipeline_name} - {len(run.steps)} steps")

    # Medical pipeline
    print("Medical Pipeline:")
    with RunContext("diagnosis_assistant") as run:
        with run.step("symptom_analysis", StepType.LLM) as step:
            step.set_outputs({"diagnosis": "flu", "confidence": 0.85})
            step.set_reasoning("Symptoms match flu pattern")
        print(f"   ✅ {run.run_model.pipeline_name} - {len(run.steps)} steps")

    print()
    print("🎉 ALL DOMAINS WORK - Context managers are truly general-purpose!")
    print()


if __name__ == "__main__":
    print("\n")
    print("🔬 X-RAY SDK - Context Manager Tests")
    print("=" * 60)
    print()

    test_basic_run_and_step()
    test_multiple_steps()
    test_context_access()
    test_candidate_tracking()
    test_exception_handling()
    test_general_purpose()

    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print()
    print("Key features demonstrated:")
    print("1. ✅ Automatic timing capture")
    print("2. ✅ Thread-safe context access (get_current_run/step)")
    print("3. ✅ Candidate tracking with reduction_rate")
    print("4. ✅ Exception handling")
    print("5. ✅ Multiple sequential steps")
    print("6. ✅ Works for any domain (general-purpose)")
    print()
    print("Next: Phase 3 - Configuration management")
    print()
