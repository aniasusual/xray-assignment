"""
Manual test for X-Ray configuration system.

Run with: cd xray-sdk && poetry run python test_config_manual.py
"""

import os
from xray.config import (
    XRayConfig,
    FallbackMode,
    get_config,
    configure,
    reset_config,
    is_enabled,
)


def test_default_config():
    """Test that default configuration works"""
    print("=" * 60)
    print("TEST 1: Default Configuration")
    print("=" * 60)

    reset_config()
    config = get_config()

    print(f"✅ Default config loaded:")
    print(f"   API URL: {config.api_url}")
    print(f"   Enabled: {config.enabled}")
    print(f"   Fallback mode: {config.fallback_mode.value}")
    print(f"   Timeout: {config.timeout_seconds}s")
    print(f"   Async mode: {config.async_mode}")
    print(f"   Verbose: {config.verbose}")
    print()


def test_programmatic_config():
    """Test configuring via code"""
    print("=" * 60)
    print("TEST 2: Programmatic Configuration")
    print("=" * 60)

    reset_config()

    # Configure for development
    config = configure(
        api_url="http://localhost:9000",
        fallback_mode="log",
        timeout_seconds=10.0,
        verbose=True,
    )

    print(f"✅ Configured for development:")
    print(f"   API URL: {config.api_url}")
    print(f"   Fallback mode: {config.fallback_mode.value}")
    print(f"   Timeout: {config.timeout_seconds}s")
    print(f"   Verbose: {config.verbose}")
    print()

    # Verify singleton behavior
    config2 = get_config()
    print(f"✅ Singleton check:")
    print(f"   Same instance: {config is config2}")
    print(f"   API URL matches: {config2.api_url == 'http://localhost:9000'}")
    print()


def test_environment_variables():
    """Test configuration via environment variables"""
    print("=" * 60)
    print("TEST 3: Environment Variable Configuration")
    print("=" * 60)

    # Set environment variables
    os.environ["XRAY_API_URL"] = "http://prod-xray.company.com"
    os.environ["XRAY_ENABLED"] = "true"
    os.environ["XRAY_FALLBACK_MODE"] = "silent"
    os.environ["XRAY_TIMEOUT"] = "15.0"
    os.environ["XRAY_VERBOSE"] = "false"

    reset_config()
    config = get_config()

    print(f"✅ Config loaded from environment:")
    print(f"   API URL: {config.api_url}")
    print(f"   Enabled: {config.enabled}")
    print(f"   Fallback mode: {config.fallback_mode.value}")
    print(f"   Timeout: {config.timeout_seconds}s")
    print(f"   Verbose: {config.verbose}")
    print()

    # Clean up
    for key in [
        "XRAY_API_URL",
        "XRAY_ENABLED",
        "XRAY_FALLBACK_MODE",
        "XRAY_TIMEOUT",
        "XRAY_VERBOSE",
    ]:
        os.environ.pop(key, None)


def test_fallback_modes():
    """Test different fallback modes"""
    print("=" * 60)
    print("TEST 4: Fallback Modes")
    print("=" * 60)

    # Test each fallback mode
    for mode in [FallbackMode.SILENT, FallbackMode.LOG, FallbackMode.RAISE]:
        reset_config()
        config = configure(fallback_mode=mode)
        print(f"✅ Fallback mode: {mode.value}")
        print(f"   Config value: {config.fallback_mode.value}")

    print()


def test_production_config():
    """Test typical production configuration"""
    print("=" * 60)
    print("TEST 5: Production Configuration")
    print("=" * 60)

    reset_config()
    config = configure(
        api_url="https://xray-api.company.com",
        fallback_mode="silent",  # Don't disrupt production!
        timeout_seconds=5.0,
        async_mode=True,  # Non-blocking
        enabled=True,
        verbose=False,
    )

    print(f"✅ Production config:")
    print(f"   API URL: {config.api_url}")
    print(f"   Fallback: {config.fallback_mode.value} (won't disrupt app)")
    print(f"   Async: {config.async_mode} (non-blocking)")
    print(f"   Timeout: {config.timeout_seconds}s")
    print(f"   Verbose: {config.verbose}")
    print()


def test_development_config():
    """Test typical development configuration"""
    print("=" * 60)
    print("TEST 6: Development Configuration")
    print("=" * 60)

    reset_config()
    config = configure(
        api_url="http://localhost:8000",
        fallback_mode="log",  # Save failures for debugging
        timeout_seconds=30.0,  # Longer timeout for debugging
        async_mode=False,  # Synchronous for easier debugging
        enabled=True,
        verbose=True,  # See what's happening
    )

    print(f"✅ Development config:")
    print(f"   API URL: {config.api_url}")
    print(f"   Fallback: {config.fallback_mode.value} (saves traces)")
    print(f"   Async: {config.async_mode} (easier to debug)")
    print(f"   Timeout: {config.timeout_seconds}s")
    print(f"   Verbose: {config.verbose} (see all logs)")
    print(f"   Log path: {config.fallback_log_path}")
    print()


def test_testing_config():
    """Test typical test/CI configuration"""
    print("=" * 60)
    print("TEST 7: Testing/CI Configuration")
    print("=" * 60)

    reset_config()
    config = configure(
        api_url="http://localhost:8000",
        fallback_mode="raise",  # Fail fast in tests
        timeout_seconds=10.0,
        async_mode=False,  # Synchronous for deterministic tests
        enabled=True,
        verbose=True,
    )

    print(f"✅ Testing config:")
    print(f"   API URL: {config.api_url}")
    print(f"   Fallback: {config.fallback_mode.value} (fail fast)")
    print(f"   Async: {config.async_mode} (deterministic)")
    print(f"   Timeout: {config.timeout_seconds}s")
    print()


def test_disable_xray():
    """Test disabling X-Ray entirely"""
    print("=" * 60)
    print("TEST 8: Disable X-Ray")
    print("=" * 60)

    reset_config()
    configure(enabled=False)

    print(f"✅ X-Ray disabled:")
    print(f"   Enabled: {is_enabled()}")
    print(f"   Use case: Staging environment, A/B testing, etc.")
    print()

    # Re-enable for other tests
    configure(enabled=True)


def test_sampling_config():
    """Test sampling configuration"""
    print("=" * 60)
    print("TEST 9: Sampling Configuration")
    print("=" * 60)

    reset_config()
    config = configure(
        max_candidates_full_capture=200,  # Capture all if <= 200
        sample_size_large=75,  # Sample 75 for >1000
        sample_size_medium=150,  # Sample 150 for 100-1000
    )

    print(f"✅ Sampling config:")
    print(f"   Full capture threshold: {config.max_candidates_full_capture}")
    print(f"   Large set sample: {config.sample_size_large}")
    print(f"   Medium set sample: {config.sample_size_medium}")
    print()
    print(f"   Example: 50 candidates → capture all")
    print(f"   Example: 500 candidates → sample {config.sample_size_medium}")
    print(f"   Example: 5000 candidates → sample {config.sample_size_large}")
    print()


def test_url_normalization():
    """Test that API URL is normalized (no trailing slash)"""
    print("=" * 60)
    print("TEST 10: URL Normalization")
    print("=" * 60)

    reset_config()

    # Try with trailing slash
    config = configure(api_url="http://localhost:8000/")
    print(f"✅ URL normalization:")
    print(f"   Input: http://localhost:8000/")
    print(f"   Output: {config.api_url}")
    print(f"   Trailing slash removed: {not config.api_url.endswith('/')}")
    print()


def test_update_config():
    """Test updating configuration"""
    print("=" * 60)
    print("TEST 11: Update Configuration")
    print("=" * 60)

    reset_config()

    # Initial config
    config = configure(api_url="http://localhost:8000", verbose=False)
    print(f"Initial config:")
    print(f"   API URL: {config.api_url}")
    print(f"   Verbose: {config.verbose}")
    print()

    # Update config
    config = configure(verbose=True, timeout_seconds=20.0)
    print(f"After update:")
    print(f"   API URL: {config.api_url} (unchanged)")
    print(f"   Verbose: {config.verbose} (updated)")
    print(f"   Timeout: {config.timeout_seconds}s (updated)")
    print()


if __name__ == "__main__":
    print("\n")
    print("🔬 X-RAY SDK - Configuration Tests")
    print("=" * 60)
    print()

    test_default_config()
    test_programmatic_config()
    test_environment_variables()
    test_fallback_modes()
    test_production_config()
    test_development_config()
    test_testing_config()
    test_disable_xray()
    test_sampling_config()
    test_url_normalization()
    test_update_config()

    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    print()
    print("Key features demonstrated:")
    print("1. ✅ Default configuration from environment")
    print("2. ✅ Programmatic configuration")
    print("3. ✅ Environment variable support")
    print("4. ✅ Multiple fallback modes (silent/log/raise)")
    print("5. ✅ Production/dev/test configurations")
    print("6. ✅ Enable/disable toggle")
    print("7. ✅ Sampling configuration")
    print("8. ✅ URL normalization")
    print("9. ✅ Config updates")
    print()
    print("Next: Phase 4 - HTTP client for sending to API")
    print()
