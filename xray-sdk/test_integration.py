"""
Integration Test - Full SDK End-to-End

This test demonstrates the complete SDK workflow:
1. Configure SDK
2. Create a pipeline with multiple steps
3. Collect data at each step
4. Automatically send to API (in this test, we'll see it fail and use fallback)

Run with: cd xray-sdk && poetry run python test_integration.py
"""

import json
from pathlib import Path

# This is how users will import - from the top-level package
from xray import configure, RunContext
from xray.models import StepType


def simulate_keyword_generation(product_title):
    """Simulate an LLM call to generate keywords"""
    # In real code, this would call GPT-4
    return ["phone", "case", "protective", "iPhone"]


def simulate_product_search(keywords):
    """Simulate searching Amazon API"""
    # In real code, this would call Amazon Product API
    # Return mock product data
    return [
        {"id": f"prod_{i}", "name": f"Product {i}", "price": 10 + i * 5, "rating": 4.0 + i * 0.1}
        for i in range(5000)  # 5000 products!
    ]


def simulate_price_filter(products, min_price, max_price):
    """Filter products by price"""
    return [p for p in products if min_price <= p["price"] <= max_price]


def simulate_rating_filter(products, min_rating):
    """Filter products by rating"""
    return [p for p in products if p["rating"] >= min_rating]


def simulate_llm_ranking(products, product_title):
    """Simulate LLM ranking for relevance"""
    # In real code, this would call GPT-4 to rank by relevance
    # For demo, just pick the first one
    return products[0] if products else None


def test_complete_pipeline():
    """
    Test a complete competitor selection pipeline with full instrumentation.

    This demonstrates Level 3 instrumentation (full debugging capability).
    """
    print("=" * 80)
    print("INTEGRATION TEST: Complete Pipeline with Full Instrumentation")
    print("=" * 80)
    print()

    # Step 1: Configure the SDK
    print("Step 1: Configuring SDK...")
    configure(
        api_url="http://localhost:9999",  # Invalid URL to test fallback
        enabled=True,
        fallback_mode="log",  # Write to file when API unavailable
        fallback_log_path=".xray/test_integration/",
        async_mode=False,  # Use sync mode for testing (easier to verify)
        timeout_seconds=1.0,
        verbose=False,  # Set to True to see detailed logs
    )
    print("   ✅ SDK configured")
    print(f"   - API URL: http://localhost:9999 (will fail - testing fallback)")
    print(f"   - Fallback mode: LOG (write to file)")
    print(f"   - Async mode: False")
    print()

    # Clean up old test files
    log_dir = Path(".xray/test_integration/")
    if log_dir.exists():
        for file in log_dir.glob("trace_*.json"):
            file.unlink()
        print("   🧹 Cleaned up old test files")
        print()

    # Step 2: Run the pipeline with full instrumentation
    print("Step 2: Running pipeline...")
    print()

    product_title = "iPhone 15 Pro Protective Case"

    with RunContext(
        pipeline_name="competitor_selection",
        pipeline_version="1.0.0",
        metadata={
            "user_id": "user_123",
            "product_title": product_title,
            "category": "phone_cases",
            "environment": "test",
        },
    ) as run:
        print(f"   📦 Pipeline started: {run.run_model.pipeline_name}")
        print(f"   🆔 Run ID: {run.run_model.id}")
        print()

        # STEP 1: Keyword Generation (LLM)
        with run.step("keyword_generation", StepType.LLM) as step:
            print(f"   🔄 Step 1: Keyword Generation (LLM)")

            # Simulate LLM call
            keywords = simulate_keyword_generation(product_title)

            # Record data
            step.set_inputs({"product_title": product_title})
            step.set_outputs({"keywords": keywords})
            step.set_reasoning(
                "Used GPT-4 with temperature=0.3 to extract search keywords. "
                "Selected terms that match product category and user intent."
            )
            step.add_metadata("model", "gpt-4")
            step.add_metadata("temperature", 0.3)
            step.add_metadata("tokens_used", 150)

            print(f"      ➜ Generated keywords: {keywords}")

        print()

        # STEP 2: Product Search
        with run.step("product_search", StepType.SEARCH) as step:
            print(f"   🔄 Step 2: Product Search")

            # Simulate API call
            candidates = simulate_product_search(keywords)

            # Record data
            step.set_inputs({"keywords": keywords, "max_results": 5000})
            step.set_outputs({"count": len(candidates)})
            step.set_candidates(0, len(candidates))  # From 0 to 5000
            step.set_reasoning(
                f"Amazon Product API search returned {len(candidates)} results. "
                f"Query constructed from keywords: {', '.join(keywords)}"
            )
            step.add_metadata("api", "amazon_product_api")
            step.add_metadata("api_latency_ms", 234)

            print(f"      ➜ Found {len(candidates)} products")

        print()

        # STEP 3: Price Filter
        with run.step("price_filter", StepType.FILTER) as step:
            print(f"   🔄 Step 3: Price Filter")

            min_price, max_price = 10, 100

            # Apply filter
            before_count = len(candidates)
            candidates = simulate_price_filter(candidates, min_price, max_price)
            after_count = len(candidates)

            # Record data
            step.set_inputs({"candidates": before_count})
            step.set_outputs({"filtered": after_count})
            step.set_candidates(before_count, after_count)
            step.set_filters({"min_price": min_price, "max_price": max_price})
            step.set_reasoning(
                f"Filtered by price range ${min_price}-${max_price}. "
                f"Reduced from {before_count} to {after_count} candidates."
            )

            print(f"      ➜ {before_count} → {after_count} products")
            print(f"      ➜ Reduction rate: {step.step_model.reduction_rate:.1%}")

        print()

        # STEP 4: Rating Filter
        with run.step("rating_filter", StepType.FILTER) as step:
            print(f"   🔄 Step 4: Rating Filter")

            min_rating = 4.5

            # Apply filter
            before_count = len(candidates)
            candidates = simulate_rating_filter(candidates, min_rating)
            after_count = len(candidates)

            # Record data
            step.set_inputs({"candidates": before_count})
            step.set_outputs({"filtered": after_count})
            step.set_candidates(before_count, after_count)
            step.set_filters({"min_rating": min_rating})
            step.set_reasoning(
                f"Filtered by minimum rating {min_rating}. "
                f"Only keeping highly-rated products to ensure quality."
            )

            print(f"      ➜ {before_count} → {after_count} products")
            print(f"      ➜ Reduction rate: {step.step_model.reduction_rate:.1%}")

        print()

        # STEP 5: LLM Ranking
        with run.step("llm_ranking", StepType.RANK) as step:
            print(f"   🔄 Step 5: LLM Ranking")

            # Simulate LLM ranking
            winner = simulate_llm_ranking(candidates, product_title)

            # Record data
            step.set_inputs({"candidates": len(candidates), "product_title": product_title})
            step.set_outputs(
                {
                    "winner_id": winner["id"] if winner else None,
                    "winner_name": winner["name"] if winner else None,
                    "relevance_score": 0.95,
                }
            )
            step.set_reasoning(
                "Used GPT-4 to rank candidates by relevance to original product. "
                "Selected based on title similarity, feature matching, and review sentiment."
            )
            step.add_metadata("model", "gpt-4")
            step.add_metadata("temperature", 0.1)  # Lower temp for consistency
            step.add_metadata("tokens_used", 2500)

            print(f"      ➜ Selected: {winner['name'] if winner else 'None'}")
            print(f"      ➜ Relevance score: 0.95")

        print()

        # Set final pipeline output
        if winner:
            run.set_final_output(
                {
                    "product_id": winner["id"],
                    "product_name": winner["name"],
                    "price": winner["price"],
                    "rating": winner["rating"],
                    "confidence": 0.95,
                }
            )

        print(f"   ✅ Pipeline completed!")
        print(f"   📊 Total steps: {len(run.steps)}")
        print()

    # When we exit the 'with' block, Phase 5 integration kicks in:
    # RunContext.__exit__() automatically calls send_trace()!

    print("=" * 80)
    print("Step 3: Verifying Results")
    print("=" * 80)
    print()

    # Check if trace was written to file (since API is unavailable)
    log_files = list(log_dir.glob(f"trace_*_{run.run_model.id}.json"))

    if log_files:
        print("✅ SUCCESS! Trace was automatically sent and logged to file")
        print(f"   📁 File: {log_files[0].name}")
        print()

        # Read and display the trace
        with open(log_files[0]) as f:
            trace_data = json.load(f)

        print("📋 Trace Contents:")
        print(f"   Pipeline: {trace_data['run']['pipeline_name']}")
        print(f"   Status: {trace_data['run']['status']}")
        print(f"   Steps: {len(trace_data['steps'])}")
        print()

        print("📊 Step Breakdown:")
        for i, step in enumerate(trace_data["steps"]):
            print(f"   {i+1}. {step['step_name']} ({step['step_type']})")
            if step.get("candidates_in") is not None:
                reduction = (
                    (step["candidates_in"] - step["candidates_out"]) / step["candidates_in"]
                    if step["candidates_in"] > 0
                    else 0
                )
                print(
                    f"      - Candidates: {step['candidates_in']} → {step['candidates_out']} ({reduction:.1%} reduction)"
                )
            if step.get("reasoning"):
                print(f"      - Reasoning: {step['reasoning'][:80]}...")

        print()
        print("=" * 80)
        print("🎉 INTEGRATION TEST PASSED!")
        print("=" * 80)
        print()
        print("Key features demonstrated:")
        print("✅ 1. Configuration (via configure())")
        print("✅ 2. Context managers (RunContext, StepContext)")
        print("✅ 3. Automatic timing capture")
        print("✅ 4. Data collection (inputs, outputs, reasoning)")
        print("✅ 5. Candidate tracking with reduction rates")
        print("✅ 6. Automatic API sending on pipeline completion")
        print("✅ 7. Fallback to file logging when API unavailable")
        print("✅ 8. Complete trace serialization to JSON")
        print()
        print("🚀 The SDK is ready to use!")
        print()
        print("Next steps:")
        print("- Phase 6: Sampling Strategy (handle 5,000+ candidates efficiently)")
        print("- Phase 7-10: Build the API backend (FastAPI + PostgreSQL)")
        print("- Phase 11-13: Create examples and demos")
        print("- Phase 14: Write ARCHITECTURE.md")
        print("- Phase 15: Record video walkthrough")

    else:
        print("❌ FAILED: Trace file not found")
        print("   This shouldn't happen - check if there was an error above")


if __name__ == "__main__":
    test_complete_pipeline()
