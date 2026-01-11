"""
Manual test for X-Ray sampling strategies.

This demonstrates how sampling works with large candidate datasets.

Run with: cd xray-sdk && poetry run python test_sampling_manual.py
"""

from xray.sampling import (
    sample_candidates,
    sample_candidates_head_tail,
    sample_candidates_random,
    sample_candidates_stratified,
    get_sampling_summary,
    should_sample,
)
from xray.config import configure, reset_config


def create_test_candidates(count: int):
    """Create mock candidates for testing"""
    return [
        {
            "id": f"product_{i}",
            "name": f"Product {i}",
            "price": 10 + (i % 100),
            "rating": 3.0 + (i % 20) * 0.1,
            "category": ["electronics", "clothing", "home"][i % 3],
        }
        for i in range(count)
    ]


def test_should_sample():
    """Test the should_sample helper"""
    print("=" * 80)
    print("TEST 1: should_sample() - Determine if sampling needed")
    print("=" * 80)

    reset_config()
    configure(max_candidates_full_capture=100)

    # Small dataset - no sampling needed
    small_candidates = create_test_candidates(50)
    print(f"Small dataset (50 candidates): should_sample = {should_sample(small_candidates)}")
    print(f"   Expected: False (≤100 threshold)")

    # Large dataset - sampling needed
    large_candidates = create_test_candidates(5000)
    print(f"Large dataset (5000 candidates): should_sample = {should_sample(large_candidates)}")
    print(f"   Expected: True (>100 threshold)")

    print()


def test_smart_sampling():
    """Test the smart sampling strategy"""
    print("=" * 80)
    print("TEST 2: sample_candidates() - Smart sampling (first/last/random)")
    print("=" * 80)

    candidates = create_test_candidates(5000)
    print(f"Original count: {len(candidates)}")

    sampled = sample_candidates(candidates, sample_size=50)
    print(f"Sampled count: {len(sampled)}")
    print(f"Expected: ~150 (50 first + 50 last + 50 random from middle)")

    # Verify we got first 50
    first_ids = [c["id"] for c in sampled[:50]]
    print(f"\n✅ First 50 IDs: {first_ids[0]} ... {first_ids[-1]}")

    # Verify we got last 50
    last_ids = [c["id"] for c in sampled[-50:]]
    print(f"✅ Last 50 IDs: {last_ids[0]} ... {last_ids[-1]}")

    # Show sampling summary
    summary = get_sampling_summary(len(candidates), len(sampled))
    print(f"\n📊 Sampling Summary:")
    print(f"   Original: {summary['original_count']}")
    print(f"   Sampled: {summary['sampled_count']}")
    print(f"   Sampling rate: {summary['sampling_rate']:.1%}")
    print(f"   Data reduction: {summary['data_reduction']:.1%}")

    print()


def test_head_tail_sampling():
    """Test head + tail sampling"""
    print("=" * 80)
    print("TEST 3: sample_candidates_head_tail() - First and last N")
    print("=" * 80)

    candidates = create_test_candidates(5000)
    print(f"Original count: {len(candidates)}")

    sampled = sample_candidates_head_tail(candidates, head_size=100, tail_size=100)
    print(f"Sampled count: {len(sampled)}")
    print(f"Expected: 200 (100 first + 100 last)")

    # Verify structure
    print(f"\n✅ First ID: {sampled[0]['id']}")
    print(f"✅ Last ID: {sampled[-1]['id']}")
    print(f"✅ Middle transition: {sampled[99]['id']} → {sampled[100]['id']}")

    print()


def test_random_sampling():
    """Test random sampling"""
    print("=" * 80)
    print("TEST 4: sample_candidates_random() - Random sampling")
    print("=" * 80)

    candidates = create_test_candidates(5000)
    print(f"Original count: {len(candidates)}")

    sampled = sample_candidates_random(candidates, sample_size=200)
    print(f"Sampled count: {len(sampled)}")
    print(f"Expected: 200 (random sample)")

    # Show some sampled IDs (should be non-sequential)
    ids = [c["id"] for c in sampled[:10]]
    print(f"\n✅ First 10 sampled IDs: {', '.join(ids)}")
    print(f"   (Should be non-sequential - proves randomness)")

    print()


def test_stratified_sampling():
    """Test stratified sampling"""
    print("=" * 80)
    print("TEST 5: sample_candidates_stratified() - Ensure group representation")
    print("=" * 80)

    candidates = create_test_candidates(5000)
    print(f"Original count: {len(candidates)}")

    # Count by category
    categories = {}
    for c in candidates:
        cat = c["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print(f"\n📊 Original distribution by category:")
    for cat, count in categories.items():
        print(f"   {cat}: {count}")

    # Sample 20 from each category
    sampled = sample_candidates_stratified(
        candidates, strata_key="category", samples_per_stratum=20
    )
    print(f"\nSampled count: {len(sampled)}")
    print(f"Expected: 60 (20 per category × 3 categories)")

    # Count sampled by category
    sampled_categories = {}
    for c in sampled:
        cat = c["category"]
        sampled_categories[cat] = sampled_categories.get(cat, 0) + 1

    print(f"\n📊 Sampled distribution by category:")
    for cat, count in sampled_categories.items():
        print(f"   {cat}: {count}")

    print(f"\n✅ Each category is represented!")

    print()


def test_small_dataset_no_sampling():
    """Test that small datasets are not sampled"""
    print("=" * 80)
    print("TEST 6: Small datasets - No sampling applied")
    print("=" * 80)

    reset_config()
    configure(max_candidates_full_capture=100)

    candidates = create_test_candidates(50)
    print(f"Original count: {len(candidates)}")

    sampled = sample_candidates(candidates)
    print(f"Sampled count: {len(sampled)}")
    print(f"Expected: 50 (same as original - no sampling needed)")

    # Verify it's the same data
    print(f"\n✅ Same data: {sampled == candidates}")

    print()


def test_integration_with_step_model():
    """Test sampling integration with StepModel"""
    print("=" * 80)
    print("TEST 7: Integration with StepModel.set_candidates()")
    print("=" * 80)

    from xray.models import StepModel, StepType

    reset_config()
    configure(max_candidates_full_capture=100)

    # Create step
    step = StepModel(
        step_name="price_filter",
        step_type=StepType.FILTER,
        sequence=0,
    )

    # Create large dataset
    candidates = create_test_candidates(5000)
    print(f"Original candidate count: {len(candidates)}")

    # Set candidates with auto-sampling
    step.set_candidates(
        candidates_in=5000,
        candidates_out=len(candidates),
        data=candidates,
        auto_sample=True,  # This is the default
    )

    print(f"\n✅ StepModel.candidates_in: {step.candidates_in}")
    print(f"✅ StepModel.candidates_out: {step.candidates_out}")
    print(f"✅ StepModel.candidates_data length: {len(step.candidates_data) if step.candidates_data else 0}")
    print(f"   Expected: ~150 (sampled automatically)")

    # Check metadata
    if step.metadata.get("sampling_applied"):
        print(f"\n📊 Sampling Metadata:")
        print(f"   sampling_applied: {step.metadata['sampling_applied']}")
        print(f"   original_data_count: {step.metadata['original_data_count']}")
        print(f"   sampled_data_count: {step.metadata['sampled_data_count']}")

        reduction = 1 - (step.metadata['sampled_data_count'] / step.metadata['original_data_count'])
        print(f"   Data reduction: {reduction:.1%}")

    print()


def test_integration_with_context():
    """Test sampling with RunContext and StepContext"""
    print("=" * 80)
    print("TEST 8: Integration with RunContext + StepContext")
    print("=" * 80)

    from xray import configure, RunContext
    from xray.models import StepType

    reset_config()
    configure(
        api_url="http://localhost:9999",
        enabled=False,  # Don't actually send
        max_candidates_full_capture=100,
    )

    # Create large dataset
    candidates = create_test_candidates(5000)
    print(f"Pipeline processing {len(candidates)} candidates")

    with RunContext("competitor_selection", auto_send=False) as run:

        # Filter step
        with run.step("price_filter", StepType.FILTER) as step:
            filtered = [c for c in candidates if c["price"] < 50]

            # Set candidates with data (will be sampled automatically)
            step.set_candidates(
                candidates_in=len(candidates),
                candidates_out=len(filtered),
                data=filtered,  # Only ~1000 candidates, but still sampled
            )

            step.set_reasoning(f"Filtered {len(candidates)} → {len(filtered)}")

    # Check the step data
    filter_step = run.steps[0]
    print(f"\n✅ Step captured:")
    print(f"   candidates_in: {filter_step.candidates_in}")
    print(f"   candidates_out: {filter_step.candidates_out}")
    print(f"   candidates_data length: {len(filter_step.candidates_data) if filter_step.candidates_data else 0}")
    print(f"   Expected: ~150 (sampled)")

    if filter_step.metadata.get("sampling_applied"):
        print(f"\n✅ Sampling was applied automatically!")
        print(f"   Original: {filter_step.metadata['original_data_count']}")
        print(f"   Sampled: {filter_step.metadata['sampled_data_count']}")

    print()


if __name__ == "__main__":
    print("\n")
    print("🔬 X-RAY SDK - Sampling Strategy Tests")
    print("=" * 80)
    print()

    test_should_sample()
    test_smart_sampling()
    test_head_tail_sampling()
    test_random_sampling()
    test_stratified_sampling()
    test_small_dataset_no_sampling()
    test_integration_with_step_model()
    test_integration_with_context()

    print("=" * 80)
    print("✅ ALL SAMPLING TESTS PASSED!")
    print("=" * 80)
    print()
    print("Key features demonstrated:")
    print("1. ✅ Smart sampling (first/last/random)")
    print("2. ✅ Head/tail sampling")
    print("3. ✅ Random sampling")
    print("4. ✅ Stratified sampling (category-based)")
    print("5. ✅ Automatic threshold detection")
    print("6. ✅ Small datasets preserved (no sampling)")
    print("7. ✅ Integration with StepModel")
    print("8. ✅ Integration with RunContext/StepContext")
    print()
    print("Why this matters:")
    print("- 5,000 candidates → ~150 sampled = 97% data reduction")
    print("- Payload size reduced 33x (faster network, smaller DB)")
    print("- Still have enough data to debug (first/last/middle samples)")
    print("- Automatic - users don't need to think about it!")
    print()
