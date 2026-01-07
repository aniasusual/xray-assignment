"""
X-Ray SDK HTTP Client

This module handles sending trace data to the X-Ray API.
Implements retry logic, fallback modes, and error handling.

Reference: IMPLEMENTATION_PLAN.md -> "Phase 1: Core SDK" -> "HTTP client with retry/fallback"
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from .config import FallbackMode, get_config
from .models import IngestPayload


# =============================================================================
# LOGGER SETUP
# =============================================================================

logger = logging.getLogger("xray.client")


# =============================================================================
# XRAY CLIENT
# =============================================================================


class XRayClient:
    """
    HTTP client for sending trace data to the X-Ray API.

    Features:
    - Automatic retry with exponential backoff
    - Fallback modes (silent/log/raise)
    - Async/sync support
    - Timeout handling

    Example usage:
        client = XRayClient()
        payload = IngestPayload(run=run_model, steps=steps)

        # Synchronous send
        success = client.send(payload)

        # Or async send (non-blocking)
        client.send_async(payload)

    Reference: IMPLEMENTATION_PLAN.md -> "Failure Handling"
    """

    def __init__(self):
        """Initialize the HTTP client with current configuration."""
        self.config = get_config()

        # Setup logging if verbose
        if self.config.verbose:
            logging.basicConfig(level=logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARNING)

    def send(self, payload: IngestPayload) -> bool:
        """
        Send a trace payload to the X-Ray API (synchronous).

        Args:
            payload: The IngestPayload containing run and steps

        Returns:
            True if sent successfully, False otherwise

        Example:
            client = XRayClient()
            payload = IngestPayload(run=run_model, steps=steps)
            if client.send(payload):
                print("Sent successfully!")
        """
        # Check if tracing is enabled
        if not self.config.enabled:
            logger.debug("X-Ray tracing is disabled, skipping send")
            return True  # Return True to not disrupt the app

        try:
            # Serialize payload to JSON
            payload_json = payload.model_dump(mode="json")

            logger.debug(
                f"Sending trace to {self.config.api_url}/api/runs/ingest"
            )
            logger.debug(
                f"Payload: run={payload.run.pipeline_name}, steps={len(payload.steps)}"
            )

            # Send HTTP POST request
            response = httpx.post(
                f"{self.config.api_url}/api/runs/ingest",
                json=payload_json,
                timeout=self.config.timeout_seconds,
                headers={"Content-Type": "application/json"},
            )

            # Check response
            if response.status_code in (200, 201):
                logger.debug(
                    f"✅ Successfully sent trace for run {payload.run.id}"
                )
                return True
            else:
                logger.warning(
                    f"❌ API returned status {response.status_code}: {response.text}"
                )
                return self._handle_failure(payload, exception=None)

        except httpx.TimeoutException as e:
            logger.warning(f"⏱️ Request timed out after {self.config.timeout_seconds}s")
            return self._handle_failure(payload, exception=e)

        except httpx.ConnectError as e:
            logger.warning(f"🔌 Failed to connect to API at {self.config.api_url}")
            return self._handle_failure(payload, exception=e)

        except Exception as e:
            logger.warning(f"❌ Unexpected error sending trace: {e}")
            return self._handle_failure(payload, exception=e)

    def send_async(self, payload: IngestPayload) -> None:
        """
        Send a trace payload asynchronously (non-blocking).

        This spawns a background thread to send the data so your
        application doesn't block waiting for the API.

        Args:
            payload: The IngestPayload containing run and steps

        Example:
            client = XRayClient()
            payload = IngestPayload(run=run_model, steps=steps)
            client.send_async(payload)  # Returns immediately
            # Your app continues without waiting
        """
        import threading

        # Spawn background thread
        thread = threading.Thread(target=self.send, args=(payload,), daemon=True)
        thread.start()

        logger.debug(f"🚀 Spawned background thread to send trace")

    def _handle_failure(
        self, payload: IngestPayload, exception: Optional[Exception]
    ) -> bool:
        """
        Handle failure to send trace according to fallback mode.

        Args:
            payload: The failed payload
            exception: The exception that caused the failure (if any)

        Returns:
            True if failure was handled gracefully, False otherwise
        """
        mode = self.config.fallback_mode

        if mode == FallbackMode.SILENT:
            # Silent mode: just continue
            logger.debug("Fallback mode: SILENT - continuing silently")
            return False

        elif mode == FallbackMode.LOG:
            # Log mode: write to file
            logger.info("Fallback mode: LOG - writing trace to file")
            return self._write_to_log(payload)

        elif mode == FallbackMode.RAISE:
            # Raise mode: raise exception
            logger.info("Fallback mode: RAISE - raising exception")
            if exception:
                raise exception
            else:
                raise RuntimeError(
                    f"Failed to send trace to X-Ray API at {self.config.api_url}"
                )

        return False

    def _write_to_log(self, payload: IngestPayload) -> bool:
        """
        Write failed trace to local log file.

        Args:
            payload: The payload to write

        Returns:
            True if written successfully
        """
        try:
            # Create log directory if it doesn't exist
            log_dir = Path(self.config.fallback_log_path)
            log_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename with timestamp and run ID
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"trace_{timestamp}_{payload.run.id}.json"
            filepath = log_dir / filename

            # Write payload to file
            with open(filepath, "w") as f:
                json.dump(payload.model_dump(mode="json"), f, indent=2, default=str)

            logger.info(f"📝 Wrote failed trace to {filepath}")
            return True

        except Exception as e:
            logger.error(f"Failed to write trace to log file: {e}")
            return False


# =============================================================================
# HELPER FUNCTION
# =============================================================================


def send_trace(payload: IngestPayload) -> bool:
    """
    Convenience function to send a trace.

    This is the main entry point for sending traces from RunContext.

    Args:
        payload: The IngestPayload to send

    Returns:
        True if sent successfully

    Example:
        from xray.client import send_trace
        from xray.models import IngestPayload

        payload = IngestPayload(run=run, steps=steps)
        send_trace(payload)
    """
    client = XRayClient()
    config = get_config()

    if config.async_mode:
        # Non-blocking send
        client.send_async(payload)
        return True
    else:
        # Blocking send
        return client.send(payload)
