# SDK Reference

Complete reference for the X-Ray Python SDK.

## Installation

```bash
pip install xray-sdk
```

## Configuration

### `configure(**kwargs)`

Configure the X-Ray SDK globally.

```python
from xray import configure, FallbackMode

configure(
    api_url="http://localhost:8001",
    enabled=True,
    fallback_mode=FallbackMode.SILENT,
    timeout_seconds=5.0,
    async_mode=True,
    max_candidates_full_capture=100,
    verbose=False
)
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `api_url` | `str` | `"http://localhost:8000"` | X-Ray API URL |
| `enabled` | `bool` | `True` | Enable/disable X-Ray |
| `fallback_mode` | `FallbackMode` | `SILENT` | What to do if API fails |
| `timeout_seconds` | `float` | `5.0` | HTTP timeout (1-60s) |
| `async_mode` | `bool` | `True` | Send traces async |
| `max_candidates_full_capture` | `int` | `100` | Sampling threshold |
| `verbose` | `bool` | `False` | Debug logging |

**Fallback Modes**:
- `FallbackMode.SILENT` - Continue silently (production)
- `FallbackMode.LOG` - Write to local file (development)
- `FallbackMode.RAISE` - Raise exception (testing)

**Example**:
```python
# Production
configure(
    api_url="https://xray.yourcompany.com",
    fallback_mode=FallbackMode.SILENT,
    async_mode=True
)

# Development
configure(
    api_url="http://localhost:8001",
    fallback_mode=FallbackMode.LOG,
    async_mode=False,  # Sync for easier debugging
    verbose=True
)

# Testing
configure(
    fallback_mode=FallbackMode.RAISE  # Fail fast
)
```

### `get_config()`

Get the current configuration.

```python
from xray import get_config

config = get_config()
print(config.api_url)
print(config.enabled)
```

## RunContext

Context manager for a complete pipeline execution.

### `RunContext(pipeline_name, pipeline_version="1.0.0", metadata=None, auto_send=True)`

```python
from xray import RunContext

with RunContext(
    pipeline_name="competitor-selection",
    pipeline_version="2.0.0",
    metadata={"user_id": "123", "environment": "production"}
) as run:
    # Your pipeline code
    pass
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pipeline_name` | `str` | *required* | Unique pipeline identifier |
| `pipeline_version` | `str` | `"1.0.0"` | Pipeline version |
| `metadata` | `dict` | `None` | Custom metadata |
| `auto_send` | `bool` | `True` | Send automatically on exit |

**Methods**:

#### `run.set_final_output(output: dict)`

Set the final output of the pipeline.

```python
with RunContext("search") as run:
    results = perform_search(query)
    run.set_final_output({"results": results, "count": len(results)})
```

#### `run.step(step_name: str, step_type: StepType) -> StepContext`

Create a step context (convenience method).

```python
with RunContext("pipeline") as run:
    with run.step("search", StepType.SEARCH) as step:
        # ...
        pass
```

## StepContext

Context manager for a single step in a pipeline.

### `StepContext(step_name, step_type, sequence=None, metadata=None)`

```python
from xray import StepContext, StepType

with StepContext(
    step_name="filter_by_price",
    step_type=StepType.FILTER,
    sequence=2,
    metadata={"version": "v2"}
) as step:
    # Your step code
    pass
```

**Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `step_name` | `str` | *required* | Step identifier |
| `step_type` | `StepType` | *required* | Type of step |
| `sequence` | `int` | *auto* | Order in pipeline (auto-increments) |
| `metadata` | `dict` | `None` | Custom metadata |

### Step Types

```python
from xray import StepType

StepType.LLM          # Language model calls
StepType.SEARCH       # Retrieval/search operations
StepType.FILTER       # Filtering/elimination
StepType.RANK         # Ranking/ordering
StepType.SELECT       # Final selection
StepType.TRANSFORM    # Data transformation
StepType.CUSTOM       # Custom operations
```

### Methods

#### `step.set_inputs(inputs: dict)`

Set input parameters for this step.

```python
with StepContext("search", StepType.SEARCH) as step:
    step.set_inputs({
        "query": "wireless headphones",
        "limit": 1000,
        "filters": {"price_min": 10}
    })
    results = search(query, limit=1000)
```

#### `step.set_outputs(outputs: dict)`

Set output results for this step.

```python
with StepContext("filter", StepType.FILTER) as step:
    filtered = filter_results(candidates)
    step.set_outputs({
        "filtered_count": len(filtered),
        "rejection_reasons": {
            "too_expensive": 500,
            "out_of_stock": 200
        }
    })
```

#### `step.set_reasoning(reasoning: str)`

Explain WHY this step did what it did.

```python
with StepContext("rank", StepType.RANK) as step:
    ranked = rank_by_score(candidates)
    step.set_reasoning(
        "Ranked by relevance score combining title similarity (40%), "
        "price match (30%), and rating (30%)"
    )
```

#### `step.set_candidates(candidates, previous_count=None, auto_sample=True)`

Set the candidates (items being processed).

```python
with StepContext("filter", StepType.FILTER) as step:
    filtered = filter_by_price(all_products, min_price=10, max_price=100)

    # Track candidates in/out
    step.set_candidates(
        filtered,
        previous_count=len(all_products),  # How many came in
        auto_sample=True  # Automatically sample if >100 items
    )
```

**Parameters**:
- `candidates` (list): The candidates to store
- `previous_count` (int, optional): How many candidates came INTO this step
- `auto_sample` (bool): Automatically sample if count > `max_candidates_full_capture`

**Sampling**:
- If `len(candidates) <= max_candidates_full_capture`: Stores all
- If `len(candidates) > max_candidates_full_capture`: Samples ~150 (head + tail + random)

**Example with sampling**:
```python
# 5000 candidates, but only ~150 will be stored
step.set_candidates(
    large_list_of_5000_items,
    previous_count=10000,  # 10000 came in, 5000 came out
    auto_sample=True  # Will sample to ~150
)

# Force full capture (not recommended for large lists)
step.set_candidates(
    critical_data,
    auto_sample=False  # Store all, even if >100
)
```

#### `step.set_filters_applied(filters: dict)`

Set which filters were applied in this step.

```python
with StepContext("filter", StepType.FILTER) as step:
    step.set_filters_applied({
        "min_price": 10.0,
        "max_price": 100.0,
        "category": "Electronics",
        "in_stock": True
    })
```

#### `step.set_metadata(metadata: dict)`

Set custom metadata for this step.

```python
with StepContext("llm_call", StepType.LLM) as step:
    step.set_metadata({
        "model": "gpt-4",
        "temperature": 0.7,
        "tokens_used": 1500
    })
```

## Utility Functions

### `get_current_run() -> Optional[RunContext]`

Get the currently active RunContext.

```python
from xray import get_current_run

def helper_function():
    run = get_current_run()
    if run:
        # Can access run.run_model, etc.
        pass
```

### `get_current_step() -> Optional[StepContext]`

Get the currently active StepContext.

```python
from xray import get_current_step

def helper_function():
    step = get_current_step()
    if step:
        # Can access step.step_model, etc.
        pass
```

### `send_trace(payload: IngestPayload) -> bool`

Manually send a trace (advanced usage).

```python
from xray import send_trace
from xray.models import IngestPayload, RunModel, StepModel

payload = IngestPayload(
    run=RunModel(...),
    steps=[StepModel(...)]
)

success = send_trace(payload)
```

## Data Models

### RunModel

```python
from xray.models import RunModel, RunStatus

run = RunModel(
    id=uuid4(),
    pipeline_name="my-pipeline",
    pipeline_version="1.0.0",
    start_time=datetime.utcnow(),
    status=RunStatus.RUNNING,
    metadata={"key": "value"},
    final_output=None
)

# Mark as complete
run.mark_complete(status=RunStatus.SUCCESS, final_output={"result": 42})
```

### StepModel

```python
from xray.models import StepModel, StepType

step = StepModel(
    id=uuid4(),
    step_name="search",
    step_type=StepType.SEARCH,
    sequence=0,
    start_time=datetime.utcnow(),
    inputs={"query": "test"},
    outputs={"count": 100},
    reasoning="Searched database",
    candidates_in=None,
    candidates_out=100,
    candidates_data=[...],
    filters_applied={},
    metadata={}
)

# Computed properties
duration_ms = step.duration_ms  # Milliseconds
reduction_rate = step.reduction_rate  # 0.0-1.0
```

### Enums

```python
from xray.models import RunStatus, StepType

# Run statuses
RunStatus.RUNNING
RunStatus.SUCCESS
RunStatus.FAILURE
RunStatus.PARTIAL

# Step types
StepType.LLM
StepType.SEARCH
StepType.FILTER
StepType.RANK
StepType.SELECT
StepType.TRANSFORM
StepType.CUSTOM
```

## Environment Variables

X-Ray respects these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `XRAY_API_URL` | `"http://localhost:8000"` | API URL |
| `XRAY_ENABLED` | `"true"` | Enable X-Ray |
| `XRAY_TIMEOUT` | `"5"` | HTTP timeout in seconds |
| `XRAY_ASYNC` | `"true"` | Async mode |
| `XRAY_LOG_FILE` | `None` | Fallback log file path |

**Example**:
```bash
export XRAY_API_URL="https://xray.prod.com"
export XRAY_ENABLED="true"
python my_pipeline.py
```

## Error Handling

### API Failures

```python
from xray import configure, FallbackMode

# Production: Continue silently
configure(fallback_mode=FallbackMode.SILENT)
# If API is down, pipeline continues without error

# Development: Log to file
configure(
    fallback_mode=FallbackMode.LOG,
    log_file="/tmp/xray.jsonl"
)
# If API is down, writes to /tmp/xray.jsonl

# Testing: Fail fast
configure(fallback_mode=FallbackMode.RAISE)
# If API is down, raises XRayClientError
```

### Disable X-Ray

```python
# Completely disable (zero overhead)
configure(enabled=False)

# All context managers become no-ops
with RunContext("pipeline"):  # Does nothing
    pass
```

## Performance

### Overhead

| Mode | Per Step | Per Run (10 steps) |
|------|----------|-------------------|
| Disabled | 0.01ms | 0.05ms |
| Async | 0.25ms | 2-3ms |
| Sync | 50ms+ | 500ms+ |

**Recommendation**: Always use `async_mode=True` in production.

### Sampling

X-Ray automatically samples large candidate lists to reduce bandwidth and storage.

**Default behavior**:
- ≤100 candidates: Store all
- \>100 candidates: Sample ~150 (head 50 + tail 50 + random 50)

**Configure**:
```python
configure(
    max_candidates_full_capture=50  # More aggressive sampling
)
```

**Disable sampling** (not recommended):
```python
step.set_candidates(data, auto_sample=False)
```

## Best Practices

### 1. Always Set Reasoning

```python
# ❌ Bad
with StepContext("filter", StepType.FILTER) as step:
    filtered = filter_products(candidates)
    step.set_candidates(filtered)

# ✅ Good
with StepContext("filter", StepType.FILTER) as step:
    filtered = filter_products(candidates, min_price=10)
    step.set_candidates(filtered, previous_count=len(candidates))
    step.set_reasoning("Filtered by price >= $10")
```

### 2. Use Descriptive Names

```python
# ❌ Bad
with StepContext("step1", StepType.CUSTOM):
    pass

# ✅ Good
with StepContext("filter_by_price", StepType.FILTER):
    pass
```

### 3. Track Candidate Counts

```python
# ❌ Bad
step.set_candidates(filtered)

# ✅ Good
step.set_candidates(filtered, previous_count=len(original))
```

### 4. Add Context in Metadata

```python
with RunContext(
    "search",
    metadata={
        "user_id": user.id,
        "session_id": session.id,
        "ab_test_group": "variant_b"
    }
):
    pass
```

## Troubleshooting

### Issue: High memory usage

**Solution**: X-Ray auto-samples. Check your configuration:
```python
config = get_config()
print(config.max_candidates_full_capture)  # Should be 50-200
```

### Issue: Slow pipeline

**Solution**: Ensure async mode is enabled:
```python
configure(async_mode=True)
```

### Issue: Missing data in API

**Solution**: Check if traces are being sent:
```python
configure(verbose=True)  # Enable debug logging
```

## Examples

See the [Examples Guide](./examples.md) for real-world use cases.

## Next Steps

- **[API Reference](./api-reference.md)** - Query your data
- **[Configuration Guide](./configuration.md)** - Advanced setup
- **[Best Practices](./best-practices.md)** - Tips and patterns
