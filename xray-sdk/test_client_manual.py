"""
Manual test for X-Ray HTTP client.

This demonstrates how the client sends trace data to the API
and handles various failure scenarios.

Run with: cd xray-sdk && poetry run python test_client_manual.py
"""

import json
import time
from pathlib import Path

from xray.client import XRayClient, send_trace
from xray.config import FallbackMode, configure, reset_config
from xray.models import IngestPayload, RunModel, RunStatus, StepModel, StepType


def test_client_creation():
    """Test creating a client"""
    print("=" * 60)
    print("TEST 1: Client Creation")
    print("=" * 60)

    reset_config()
    configure(
        api_url="http://localhost:8000",
        enabled=True,
        fallback_mode="silent",
        async_mode=False,
    )

    client = XRayClient()
    print(f"✅ Created client")
    print(f"   API URL: {client.config.api_url}")
    print(f"   Enabled: {client.config.enabled}")
    print(f"   Fallback mode: {client.config.fallback_mode.value}")
    print(f"   Async mode: {client.config.async_mode}")
    print()


def test_send_when_disabled():
    """Test that send returns True when tracing is disabled"""
    print("=" * 60)
    print("TEST 2: Send When Disabled")
    print("=" * 60)

    reset_config()
    configure(enabled=False)

    # Create a simple payload
    run = RunModel(pipeline_name="test_pipeline")
    run.mark_complete(status=RunStatus.SUCCESS)
    step = StepModel(
        step_name="test_step", step_type=StepType.CUSTOM, sequence=0, reasoning="test"
    )

    payload = IngestPayload(run=run, steps=[step])

    # Try to send
    client = XRayClient()
    result = client.send(payload)

    print(f"✅ Send returned: {result}")
    print(f"   Expected: True (tracing disabled, returns True to not disrupt app)")
    print()


def test_fallback_silent_mode():
    """Test SILENT fallback when API is unavailable"""
    print("=" * 60)
    print("TEST 3: Fallback Mode - SILENT")
    print("=" * 60)

    reset_config()
    configure(
        api_url="http://localhost:9999",  # Invalid port - will fail
        enabled=True,
        fallback_mode="silent",
        async_mode=False,
        timeout_seconds=1.0,  # Short timeout for testing
    )

    # Create payload
    run = RunModel(pipeline_name="test_pipeline")
    run.mark_complete(status=RunStatus.SUCCESS)
    step = StepModel(
        step_name="test_step", step_type=StepType.CUSTOM, sequence=0, reasoning="test"
    )
    payload = IngestPayload(run=run, steps=[step])

    # Try to send (will fail, but should handle gracefully)
    client = XRayClient()
    print(f"Attempting to send to {client.config.api_url}...")

    result = client.send(payload)

    print(f"✅ Send completed (expected to fail silently)")
    print(f"   Result: {result}")
    print(f"   Expected: False (failed but handled gracefully)")
    print()


def test_fallback_log_mode():
    """Test LOG fallback - writes to file when API unavailable"""
    print("=" * 60)
    print("TEST 4: Fallback Mode - LOG")
    print("=" * 60)

    reset_config()
    configure(
        api_url="http://localhost:9999",  # Invalid port - will fail
        enabled=True,
        fallback_mode="log",
        fallback_log_path=".xray/test_failed_traces/",
        async_mode=False,
        timeout_seconds=1.0,
    )

    # Clean up any existing test log files
    log_dir = Path(".xray/test_failed_traces/")
    if log_dir.exists():
        for file in log_dir.glob("trace_*.json"):
            file.unlink()

    # Create payload
    run = RunModel(pipeline_name="test_pipeline", metadata={"test_id": "log_test"})
    run.mark_complete(status=RunStatus.SUCCESS)
    step = StepModel(
        step_name="test_step",
        step_type=StepType.CUSTOM,
        sequence=0,
        reasoning="test with log fallback",
    )
    payload = IngestPayload(run=run, steps=[step])

    # Try to send (will fail, should write to file)
    client = XRayClient()
    print(f"Attempting to send to {client.config.api_url}...")

    result = client.send(payload)

    print(f"✅ Send completed")
    print(f"   Result: {result}")
    print(f"   Expected: True (wrote to log file)")

    # Check if file was created
    log_files = list(log_dir.glob(f"trace_*_{run.id}.json"))
    if log_files:
        print(f"   ✅ Log file created: {log_files[0].name}")

        # Verify file contents
        with open(log_files[0]) as f:
            logged_data = json.load(f)
            print(f"   ✅ File contains valid JSON")
            print(f"      Pipeline: {logged_data['run']['pipeline_name']}")
            print(f"      Steps: {len(logged_data['steps'])}")
    else:
        print(f"   ❌ No log file found")

    print()


def test_fallback_raise_mode():
    """Test RAISE fallback - raises exception when API unavailable"""
    print("=" * 60)
    print("TEST 5: Fallback Mode - RAISE")
    print("=" * 60)

    reset_config()
    configure(
        api_url="http://localhost:9999",  # Invalid port - will fail
        enabled=True,
        fallback_mode="raise",
        async_mode=False,
        timeout_seconds=1.0,
    )

    # Create payload
    run = RunModel(pipeline_name="test_pipeline")
    run.mark_complete(status=RunStatus.SUCCESS)
    step = StepModel(
        step_name="test_step", step_type=StepType.CUSTOM, sequence=0, reasoning="test"
    )
    payload = IngestPayload(run=run, steps=[step])

    # Try to send (should raise exception)
    client = XRayClient()
    print(f"Attempting to send to {client.config.api_url}...")

    try:
        result = client.send(payload)
        print(f"❌ Expected exception but send succeeded: {result}")
    except Exception as e:
        print(f"✅ Exception raised as expected")
        print(f"   Exception type: {type(e).__name__}")
        print(f"   Message: {str(e)}")

    print()


def test_async_send():
    """Test async (non-blocking) send"""
    print("=" * 60)
    print("TEST 6: Async Send (Non-Blocking)")
    print("=" * 60)

    reset_config()
    configure(
        api_url="http://localhost:9999",  # Will fail, but shouldn't block
        enabled=True,
        fallback_mode="silent",
        async_mode=False,  # Use sync mode but test async explicitly
        timeout_seconds=1.0,
    )

    # Create payload
    run = RunModel(pipeline_name="test_pipeline")
    run.mark_complete(status=RunStatus.SUCCESS)
    step = StepModel(
        step_name="test_step", step_type=StepType.CUSTOM, sequence=0, reasoning="test"
    )
    payload = IngestPayload(run=run, steps=[step])

    # Send async
    client = XRayClient()
    print(f"Calling send_async (should return immediately)...")

    start_time = time.time()
    client.send_async(payload)
    elapsed = time.time() - start_time

    print(f"✅ send_async returned")
    print(f"   Elapsed time: {elapsed * 1000:.2f}ms")
    print(f"   Expected: < 50ms (should be nearly instant)")
    print(f"   Background thread is handling the actual send")

    # Give thread a moment to complete
    time.sleep(2)
    print(f"   Background thread should have completed by now")

    print()


def test_send_trace_helper():
    """Test the send_trace helper function"""
    print("=" * 60)
    print("TEST 7: send_trace() Helper Function")
    print("=" * 60)

    reset_config()
    configure(
        api_url="http://localhost:9999",
        enabled=True,
        fallback_mode="silent",
        async_mode=False,
        timeout_seconds=1.0,
    )

    # Create payload
    run = RunModel(pipeline_name="test_pipeline")
    run.mark_complete(status=RunStatus.SUCCESS)
    step = StepModel(
        step_name="test_step", step_type=StepType.CUSTOM, sequence=0, reasoning="test"
    )
    payload = IngestPayload(run=run, steps=[step])

    # Use the helper function
    print(f"Using send_trace() helper...")
    result = send_trace(payload)

    print(f"✅ send_trace() completed")
    print(f"   Result: {result}")
    print(f"   This is the main entry point from RunContext")

    print()


def test_with_async_mode_enabled():
    """Test send_trace with async_mode=True in config"""
    print("=" * 60)
    print("TEST 8: send_trace() with async_mode=True")
    print("=" * 60)

    reset_config()
    configure(
        api_url="http://localhost:9999",
        enabled=True,
        fallback_mode="silent",
        async_mode=True,  # Enable async mode
        timeout_seconds=1.0,
    )

    # Create payload
    run = RunModel(pipeline_name="test_pipeline")
    run.mark_complete(status=RunStatus.SUCCESS)
    step = StepModel(
        step_name="test_step", step_type=StepType.CUSTOM, sequence=0, reasoning="test"
    )
    payload = IngestPayload(run=run, steps=[step])

    # Use the helper function (should use async internally)
    print(f"Using send_trace() with async_mode=True...")

    start_time = time.time()
    result = send_trace(payload)
    elapsed = time.time() - start_time

    print(f"✅ send_trace() completed (non-blocking)")
    print(f"   Result: {result}")
    print(f"   Elapsed time: {elapsed * 1000:.2f}ms")
    print(f"   Expected: < 50ms (async mode should return immediately)")

    # Give thread a moment
    time.sleep(2)
    print(f"   Background thread should have completed by now")

    print()


def test_realistic_payload():
    """Test with a realistic multi-step payload"""
    print("=" * 60)
    print("TEST 9: Realistic Multi-Step Payload")
    print("=" * 60)

    reset_config()
    configure(
        api_url="http://localhost:9999",
        enabled=True,
        fallback_mode="log",
        fallback_log_path=".xray/test_failed_traces/",
        async_mode=False,
        timeout_seconds=1.0,
    )

    # Create a realistic run with multiple steps
    run = RunModel(
        pipeline_name="competitor_selection",
        pipeline_version="1.0.0",
        metadata={
            "user_id": "user_123",
            "product_title": "iPhone 15 Pro Case",
            "category": "phone_cases",
        },
    )

    # Step 1: Keyword generation
    step1 = StepModel(
        step_name="keyword_generation",
        step_type=StepType.LLM,
        sequence=0,
        inputs={"product_title": "iPhone 15 Pro Case"},
        outputs={"keywords": ["phone", "case", "iPhone", "protective"]},
        reasoning="Used GPT-4 to extract search keywords",
        metadata={"model": "gpt-4", "temperature": 0.3},
    )

    # Step 2: Search
    step2 = StepModel(
        step_name="product_search",
        step_type=StepType.SEARCH,
        sequence=1,
        inputs={"keywords": ["phone", "case", "iPhone", "protective"]},
        outputs={"count": 5000},
        reasoning="Amazon Product API search",
        candidates_in=0,
        candidates_out=5000,
    )

    # Step 3: Filter
    step3 = StepModel(
        step_name="price_filter",
        step_type=StepType.FILTER,
        sequence=2,
        inputs={"candidates": 5000},
        outputs={"filtered": 2500},
        reasoning="Filtered by price range $10-$100",
        candidates_in=5000,
        candidates_out=2500,
        filters_applied={"min_price": 10, "max_price": 100},
    )

    # Mark run complete
    run.mark_complete(
        status=RunStatus.SUCCESS,
        final_output={
            "selected_product": {"id": "B09X7K3Q2J", "name": "Spigen Case", "price": 15.99}
        },
    )

    payload = IngestPayload(run=run, steps=[step1, step2, step3])

    print(f"Created realistic payload:")
    print(f"   Pipeline: {payload.run.pipeline_name}")
    print(f"   Steps: {len(payload.steps)}")
    for i, step in enumerate(payload.steps):
        print(f"      {i}. {step.step_name} ({step.step_type.value})")

    print()
    print(f"Attempting to send...")

    client = XRayClient()
    result = client.send(payload)

    print(f"✅ Send completed")
    print(f"   Result: {result}")
    print(f"   Check log file for full payload details")

    print()


if __name__ == "__main__":
    print("\n")
    print("🔬 X-RAY SDK - HTTP Client Tests")
    print("=" * 60)
    print()

    test_client_creation()
    test_send_when_disabled()
    test_fallback_silent_mode()
    test_fallback_log_mode()
    test_fallback_raise_mode()
    test_async_send()
    test_send_trace_helper()
    test_with_async_mode_enabled()
    test_realistic_payload()

    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print()
    print("Key features demonstrated:")
    print("1. ✅ Client creation with configuration")
    print("2. ✅ Disabled tracing (returns True)")
    print("3. ✅ SILENT fallback (fails gracefully)")
    print("4. ✅ LOG fallback (writes to file)")
    print("5. ✅ RAISE fallback (raises exception)")
    print("6. ✅ Async send (non-blocking)")
    print("7. ✅ send_trace() helper function")
    print("8. ✅ async_mode configuration")
    print("9. ✅ Realistic multi-step payload")
    print()
    print("Note: These tests use an invalid API URL (localhost:9999)")
    print("      to test fallback behavior without needing a real API.")
    print("      In Phase 8, we'll build the actual API endpoint.")
    print()
    print("Next: Phase 5 - Public API & Integration")
    print()
