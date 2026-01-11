#!/usr/bin/env python3
"""
Debugging Script for Competitor Selection Pipeline

This script demonstrates how to use X-Ray API to debug the competitor
selection pipeline and find the root cause of incorrect matches.

Run this AFTER running competitor_selection_demo.py
"""

import sys
import requests
import json
from typing import Optional

API_BASE = "http://127.0.0.1:8001"


def print_header(text: str, char: str = "="):
    """Print a formatted header."""
    print()
    print(char * 70)
    print(text)
    print(char * 70)
    print()


def print_section(text: str):
    """Print a section header."""
    print()
    print(f"{'─' * 70}")
    print(f"📍 {text}")
    print(f"{'─' * 70}")


def get_latest_competitor_selection_run():
    """Get the most recent competitor-selection run."""
    print_section("Step 1: Finding Latest Competitor Selection Run")

    response = requests.get(
        f"{API_BASE}/api/runs",
        params={
            "pipeline_name": "competitor-selection",
            "limit": 1
        }
    )

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        print(response.text)
        return None

    data = response.json()
    if not data["runs"]:
        print("❌ No runs found. Did you run competitor_selection_demo.py first?")
        return None

    run = data["runs"][0]
    print(f"✅ Found run: {run['id']}")
    print(f"   Pipeline: {run['pipeline_name']}")
    print(f"   Status: {run['status']}")
    print(f"   Started: {run['start_time']}")

    # Check final output
    final_output = run.get("final_output", {})
    if final_output and "selected_competitor" in final_output:
        competitor = final_output["selected_competitor"]
        print(f"\n   Final Selection:")
        print(f"     Title: {competitor['title']}")
        print(f"     Category: {competitor['category']}")

        # Check if it's a wrong match
        if "Laptop" in competitor["title"] or "Computer" in competitor["category"]:
            print(f"\n   ⚠️  PROBLEM DETECTED: Laptop stand matched for phone case!")

    return run["id"]


def analyze_run_steps(run_id: str):
    """Get and analyze all steps in the run."""
    print_section("Step 2: Retrieving Detailed Trace")

    response = requests.get(f"{API_BASE}/api/runs/{run_id}")

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code}")
        return

    data = response.json()
    run = data["run"]
    steps = data["steps"]

    print(f"✅ Retrieved {len(steps)} steps")
    print()

    # Analyze each step
    for i, step in enumerate(steps, 1):
        print(f"{'─' * 70}")
        print(f"Step {i}: {step['step_name']} ({step['step_type']})")
        print(f"{'─' * 70}")

        print(f"  Duration: {step.get('duration_ms', 0):.2f}ms")

        if step['candidates_in'] is not None and step['candidates_out'] is not None:
            reduction = step.get('reduction_rate', 0)
            print(f"  Candidates: {step['candidates_in']} → {step['candidates_out']} ({reduction*100:.1f}% reduction)")

        # Show inputs
        if step.get('inputs'):
            print(f"\n  Inputs:")
            for key, value in step['inputs'].items():
                if isinstance(value, (list, dict)) and len(str(value)) > 100:
                    print(f"    {key}: <{type(value).__name__}>")
                else:
                    print(f"    {key}: {value}")

        # Show filters applied
        if step.get('filters_applied'):
            print(f"\n  Filters Applied:")
            for key, value in step['filters_applied'].items():
                print(f"    {key}: {value}")

        # Show outputs
        if step.get('outputs'):
            print(f"\n  Outputs:")
            for key, value in step['outputs'].items():
                if isinstance(value, (list, dict)) and len(str(value)) > 100:
                    print(f"    {key}: <{type(value).__name__}>")
                else:
                    print(f"    {key}: {value}")

        # Show sampled candidates
        if step.get('candidates_data'):
            candidates = step['candidates_data']
            print(f"\n  Sample Candidates ({len(candidates)} shown):")
            for j, candidate in enumerate(candidates[:5], 1):  # Show first 5
                title = candidate.get('title', 'N/A')
                category = candidate.get('category', 'N/A')
                score = candidate.get('_relevance_score') or candidate.get('_category_similarity')
                if score:
                    print(f"    {j}. {title}")
                    print(f"       Category: {category}, Score: {score}")
                else:
                    print(f"    {j}. {title} ({category})")

        # Show reasoning
        if step.get('reasoning'):
            print(f"\n  Reasoning: {step['reasoning']}")

        print()

    return steps


def identify_root_cause(steps):
    """Analyze steps to identify the root cause."""
    print_section("Step 3: Root Cause Analysis")

    # Find the filter step
    filter_step = next((s for s in steps if s['step_name'] == 'filter_by_category'), None)
    rank_step = next((s for s in steps if s['step_name'] == 'rank_by_relevance'), None)

    if not filter_step:
        print("❌ Could not find filter_by_category step")
        return

    print("🔍 Analyzing filter_by_category step:")
    print()

    # Check threshold
    filters = filter_step.get('filters_applied', {})
    threshold = filters.get('category_similarity_threshold')

    print(f"  Threshold: {threshold}")

    if threshold and threshold < 0.5:
        print(f"  ⚠️  ISSUE #1: Threshold is too low ({threshold})!")
        print(f"     - This allows items from different categories to pass through")
        print(f"     - Recommendation: Increase to 0.7 or higher")

    # Check reduction rate
    reduction = filter_step.get('reduction_rate', 0)
    print(f"\n  Reduction Rate: {reduction*100:.1f}%")

    if reduction < 0.5:
        print(f"  ⚠️  ISSUE #2: Filter is not aggressive enough!")
        print(f"     - Only filtering out {reduction*100:.1f}% of candidates")
        print(f"     - Should filter out 70-90% for good quality")

    # Check candidates that passed
    candidates = filter_step.get('candidates_data', [])
    wrong_category_count = 0

    print(f"\n  Checking sampled candidates that passed filter:")
    for candidate in candidates[:10]:
        category = candidate.get('category', '')
        title = candidate.get('title', '')
        if 'Computer' in category or 'Laptop' in title:
            wrong_category_count += 1
            print(f"    ❌ {title} ({category})")

    if wrong_category_count > 0:
        print(f"\n  ⚠️  ISSUE #3: {wrong_category_count} wrong-category items passed filter!")

    # Analyze ranking step
    if rank_step:
        print()
        print("🔍 Analyzing rank_by_relevance step:")
        print()

        inputs = rank_step.get('inputs', {})
        boost_price = inputs.get('boost_price_match')

        if boost_price:
            print(f"  ⚠️  ISSUE #4: Price matching boost is enabled")
            print(f"     - This helps laptop stands (similar price to phone cases)")
            print(f"     - Recommendation: Disable or add category weight")

        # Show top ranked items
        candidates = rank_step.get('candidates_data', [])
        if candidates:
            print(f"\n  Top 3 ranked items:")
            for i, candidate in enumerate(candidates[:3], 1):
                title = candidate.get('title', '')
                category = candidate.get('category', '')
                score = candidate.get('_relevance_score', 0)
                print(f"    {i}. Score {score}: {title}")
                print(f"       Category: {category}")

                if i == 1 and ('Computer' in category or 'Laptop' in title):
                    print(f"       ❌ WRONG CATEGORY RANKED #1!")


def suggest_fixes():
    """Suggest how to fix the issues."""
    print_section("Step 4: Recommended Fixes")

    print("Based on the analysis, here are the fixes:")
    print()

    print("1️⃣  INCREASE CATEGORY FILTER THRESHOLD")
    print("   Change: filters_applied = {'category_similarity_threshold': 0.7}")
    print("   Impact: Will filter out 90% instead of 16%")
    print()

    print("2️⃣  ADD LLM VALIDATION STEP")
    print("   Add after ranking:")
    print("   ```python")
    print("   with StepContext('llm_validate_category', StepType.LLM) as step:")
    print("       validated = llm_check_category_match(ranked)")
    print("       step.set_reasoning('Used GPT-4 to validate category match')")
    print("   ```")
    print()

    print("3️⃣  ADJUST RANKING WEIGHTS")
    print("   - Increase category similarity weight from 0.2 to 0.5")
    print("   - Decrease price match boost or add category check")
    print()

    print("4️⃣  VERIFY FIX")
    print("   After changes, query X-Ray API:")
    print("   ```bash")
    print("   curl -X POST http://127.0.0.1:8001/api/steps/query \\")
    print("     -d '{\"step_name\": \"filter_by_category\"}'")
    print("   ```")
    print("   Compare old vs new reduction rates")


def compare_with_other_runs():
    """Show how to compare across runs."""
    print_section("Step 5: Cross-Run Comparison")

    print("Query all filter steps to find patterns:")
    print()

    response = requests.post(
        f"{API_BASE}/api/steps/query",
        json={
            "step_name": "filter_by_category",
            "pipeline_name": "competitor-selection"
        }
    )

    if response.status_code == 200:
        data = response.json()
        steps = data.get("steps", [])

        if steps:
            print(f"Found {len(steps)} filter steps:")
            print()

            avg_reduction = sum(s.get('reduction_rate', 0) for s in steps) / len(steps)
            print(f"  Average reduction rate: {avg_reduction*100:.1f}%")

            # Show distribution
            thresholds = {}
            for step in steps:
                filters = step.get('filters_applied', {})
                threshold = filters.get('category_similarity_threshold')
                if threshold:
                    thresholds[threshold] = thresholds.get(threshold, 0) + 1

            print(f"\n  Threshold distribution:")
            for threshold, count in sorted(thresholds.items()):
                print(f"    {threshold}: {count} runs")
        else:
            print("  No other runs found (this is the first one)")
    else:
        print(f"  Could not query: {response.status_code}")


def main():
    print_header("X-Ray Debugging Demo - Competitor Selection", "=")

    print("This script demonstrates how to use X-Ray to debug a")
    print("pipeline with incorrect output (phone case → laptop stand).")
    print()

    try:
        # Health check
        response = requests.get(f"{API_BASE}/health")
        if response.status_code != 200:
            print("❌ X-Ray API is not running!")
            print("   Start it with: ./start_api.sh")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("❌ X-Ray API is not running!")
        print("   Start it with: ./start_api.sh")
        sys.exit(1)

    # Step 1: Get latest run
    run_id = get_latest_competitor_selection_run()
    if not run_id:
        sys.exit(1)

    # Step 2: Analyze steps
    steps = analyze_run_steps(run_id)
    if not steps:
        sys.exit(1)

    # Step 3: Identify root cause
    identify_root_cause(steps)

    # Step 4: Suggest fixes
    suggest_fixes()

    # Step 5: Show comparison
    compare_with_other_runs()

    print_header("Analysis Complete!", "=")
    print("Time to debug: ~2 minutes")
    print("Without X-Ray: Would take hours/days")
    print()


if __name__ == "__main__":
    main()
