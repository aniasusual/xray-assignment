# Best Practices

Guidelines for getting the most value from X-Ray.

## Instrumentation

### Use Descriptive Names

**❌ Bad**:
```python
with StepContext("step1", StepType.CUSTOM):
    pass

with StepContext("process", StepType.CUSTOM):
    pass
```

**✅ Good**:
```python
with StepContext("filter_by_price", StepType.FILTER):
    pass

with StepContext("rank_by_relevance", StepType.RANK):
    pass
```

**Why**: Descriptive names make queries and debugging much easier.

### Follow Naming Convention

Use `verb_noun` pattern:
- ✅ `generate_keywords`
- ✅ `filter_by_category`
- ✅ `rank_by_score`
- ✅ `select_top_candidates`
- ❌ `keywords` (noun only)
- ❌ `filtering` (gerund)
- ❌ `step2` (generic)

### Always Set Reasoning

**❌ Bad**:
```python
with StepContext("filter", StepType.FILTER) as step:
    filtered = filter_products(candidates)
    step.set_candidates(filtered)
```

**✅ Good**:
```python
with StepContext("filter", StepType.FILTER) as step:
    filtered = filter_products(candidates, min_price=10, max_price=100)
    step.set_candidates(filtered, previous_count=len(candidates))
    step.set_reasoning(
        "Filtered products by price range $10-$100. "
        "Removed out-of-stock items. Applied category match."
    )
```

**Why**: Reasoning explains WHY, which is crucial for debugging.

### Track Candidate Counts

**❌ Bad**:
```python
step.set_candidates(filtered)  # Lost information!
```

**✅ Good**:
```python
step.set_candidates(filtered, previous_count=len(original))
# Now you can see: 5000 → 500 (90% reduction)
```

**Why**: Reduction rates help identify bottlenecks and bugs.

### Set Inputs and Outputs

**❌ Bad**:
```python
with StepContext("filter", StepType.FILTER) as step:
    filtered = filter_by_price(candidates, 10, 100)
```

**✅ Good**:
```python
with StepContext("filter", StepType.FILTER) as step:
    step.set_inputs({
        "min_price": 10,
        "max_price": 100,
        "algorithm": "simple_range"
    })

    filtered = filter_by_price(candidates, 10, 100)

    step.set_outputs({
        "filtered_count": len(filtered),
        "avg_price": sum(p.price for p in filtered) / len(filtered)
    })
```

**Why**: Makes it easy to identify which parameters caused issues.

## Configuration

### Different Settings per Environment

```python
import os
from xray import configure, FallbackMode

environment = os.getenv("ENV", "development")

if environment == "production":
    configure(
        api_url="https://xray.prod.com",
        enabled=True,
        fallback_mode=FallbackMode.SILENT,
        async_mode=True,
        max_candidates_full_capture=50  # Aggressive sampling
    )
elif environment == "development":
    configure(
        api_url="http://localhost:8001",
        enabled=True,
        fallback_mode=FallbackMode.LOG,
        log_file="/tmp/xray.jsonl",
        async_mode=False,  # Sync for easier debugging
        max_candidates_full_capture=200,  # More detail
        verbose=True
    )
else:  # testing
    configure(
        enabled=True,
        fallback_mode=FallbackMode.RAISE,  # Fail fast
        async_mode=False
    )
```

### Use Environment Variables

```python
configure(
    api_url=os.getenv("XRAY_API_URL", "http://localhost:8001"),
    enabled=os.getenv("XRAY_ENABLED", "true").lower() == "true"
)
```

## Performance

### Always Use Async Mode in Production

**❌ Bad**:
```python
configure(async_mode=False)  # Pipeline waits for X-Ray!
```

**✅ Good**:
```python
configure(async_mode=True)  # Non-blocking, <1ms overhead
```

### Let Sampling Work

**❌ Bad**:
```python
# Disabling sampling for large lists
step.set_candidates(
    list_of_10000_items,
    auto_sample=False  # 10MB payload!
)
```

**✅ Good**:
```python
# Trust the sampling
step.set_candidates(
    list_of_10000_items,
    auto_sample=True  # ~150 items stored, 97% reduction
)
```

**When to disable sampling**:
- Critical debugging (temporarily)
- Small datasets (<100 items)
- You need to see ALL rejected candidates

### Disable in Performance-Critical Paths

```python
# At module level
xray_enabled = os.getenv("XRAY_ENABLED") == "true"

def critical_function():
    if xray_enabled:
        with StepContext("critical", StepType.CUSTOM) as step:
            result = do_work()
    else:
        result = do_work()
    return result
```

Or use configuration:
```python
# Only enable for 10% of requests
configure(enabled=random.random() < 0.1)
```

## Data Quality

### Add Rich Metadata

**❌ Bad**:
```python
with RunContext("search") as run:
    pass
```

**✅ Good**:
```python
with RunContext(
    "search",
    metadata={
        "user_id": user.id,
        "session_id": session.id,
        "ab_test_variant": "new_ranking",
        "device_type": "mobile",
        "region": "us-west"
    }
) as run:
    pass
```

**Why**: Makes it easy to slice data: "Show me all failed runs for mobile users in us-west"

### Log Rejection Reasons

When filtering out candidates, capture aggregate stats:

```python
with StepContext("filter", StepType.FILTER) as step:
    rejected_reasons = {
        "too_expensive": 0,
        "out_of_stock": 0,
        "wrong_category": 0
    }

    filtered = []
    for candidate in candidates:
        if candidate.price > 100:
            rejected_reasons["too_expensive"] += 1
        elif not candidate.in_stock:
            rejected_reasons["out_of_stock"] += 1
        elif candidate.category != target_category:
            rejected_reasons["wrong_category"] += 1
        else:
            filtered.append(candidate)

    step.set_outputs({"rejection_reasons": rejected_reasons})
    step.set_candidates(filtered, previous_count=len(candidates))
```

### Capture LLM Costs

```python
with StepContext("llm_call", StepType.LLM) as step:
    step.set_inputs({"model": "gpt-4", "temperature": 0.7})

    response = llm.complete(prompt)

    step.set_outputs({
        "response": response.text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cost_usd": calculate_cost(response.usage)
    })
    step.set_reasoning(f"Used GPT-4 to {purpose}")
```

## Querying

### Use Cross-Pipeline Queries

Don't just query one pipeline. Find patterns across all:

```bash
# Find all slow LLM steps (any pipeline)
curl -X POST http://localhost:8001/api/steps/query \
  -d '{"step_type": "LLM", "min_duration_ms": 3000}'

# Find all inefficient filters (any pipeline)
curl -X POST http://localhost:8001/api/steps/query \
  -d '{"step_type": "FILTER", "max_reduction_rate": 0.3}'
```

### Build Dashboards

Query the API periodically and visualize:

```python
import requests
import matplotlib.pyplot as plt

# Get analytics
response = requests.get("http://localhost:8001/api/analytics/summary")
data = response.json()

# Plot success rate over time
plt.plot(data["runs"]["success_rate"])
plt.title("Pipeline Success Rate")
plt.show()
```

### Alert on Anomalies

```python
# Check for unusual patterns
response = requests.get("http://localhost:8001/api/analytics/summary")
data = response.json()

if data["runs"]["success_rate"] < 0.9:
    send_slack_alert(f"⚠️ Success rate dropped to {data['runs']['success_rate']}")

if data["performance"]["avg_duration_ms"] > 10000:
    send_slack_alert(f"⚠️ Pipeline slowed to {data['performance']['avg_duration_ms']}ms")
```

## Testing

### Test with X-Ray Enabled

Don't disable in tests. Use it to catch issues:

```python
import pytest
from xray import configure, FallbackMode

@pytest.fixture(autouse=True)
def setup_xray():
    configure(
        api_url="http://localhost:8001",
        enabled=True,
        fallback_mode=FallbackMode.RAISE,  # Fail if X-Ray breaks
        async_mode=False  # Sync for deterministic tests
    )

def test_pipeline():
    result = run_pipeline(input_data)
    assert result == expected_output
    # X-Ray trace is sent, can query it!
```

### Verify Instrumentation

```python
def test_instrumentation():
    with RunContext("test-pipeline") as run:
        with StepContext("test-step", StepType.FILTER) as step:
            step.set_candidates([1, 2, 3])
            step.set_reasoning("Test reasoning")

    # Verify step was recorded
    assert len(run.steps) == 1
    assert run.steps[0].step_name == "test-step"
    assert run.steps[0].reasoning == "Test reasoning"
```

## Security

### Don't Log Sensitive Data

**❌ Bad**:
```python
with StepContext("authenticate", StepType.CUSTOM) as step:
    step.set_inputs({
        "username": username,
        "password": password  # NEVER!
    })
```

**✅ Good**:
```python
with StepContext("authenticate", StepType.CUSTOM) as step:
    step.set_inputs({
        "username": username,
        "auth_method": "password"  # No sensitive data
    })
```

### Sanitize PII

```python
def sanitize_email(email: str) -> str:
    """user@example.com → u***@example.com"""
    local, domain = email.split("@")
    return f"{local[0]}***@{domain}"

with RunContext("user-pipeline", metadata={
    "user_email": sanitize_email(user.email)
}):
    pass
```

### Add Access Control

In production, add API authentication:

```python
# app/main.py
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key")

def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != os.getenv("XRAY_API_KEY"):
        raise HTTPException(403, "Invalid API key")

@app.get("/api/runs", dependencies=[Depends(verify_api_key)])
async def list_runs():
    pass
```

## Debugging

### Use Verbose Mode Locally

```python
configure(verbose=True)
```

This logs all X-Ray operations:
```
[X-Ray] Sending trace for run 550e8400...
[X-Ray] Trace sent successfully (201)
[X-Ray] Duration: 45ms
```

### Check Fallback Logs

If using `FallbackMode.LOG`:

```bash
tail -f /tmp/xray.jsonl
```

Each line is a complete trace you can upload later:

```bash
# Upload fallback logs
curl -X POST http://localhost:8001/api/runs/ingest \
  -H "Content-Type: application/json" \
  -d @/tmp/xray.jsonl
```

### Query Recent Failures

```bash
# Get last 10 failed runs
curl "http://localhost:8001/api/runs?status=FAILURE&limit=10"
```

## Common Patterns

### Conditional Steps

```python
with RunContext("pipeline") as run:
    with StepContext("search", StepType.SEARCH) as step:
        results = search(query)
        step.set_candidates(results)

    # Only filter if we have results
    if len(results) > 0:
        with StepContext("filter", StepType.FILTER) as step:
            filtered = filter_results(results)
            step.set_candidates(filtered, previous_count=len(results))
```

### Error Handling

```python
with RunContext("pipeline") as run:
    try:
        with StepContext("risky_step", StepType.CUSTOM) as step:
            result = may_fail()
            step.set_outputs({"result": result})
    except Exception as e:
        step.set_metadata({"error": str(e), "error_type": type(e).__name__})
        # X-Ray still captures the step with error info
        raise
```

### Nested Pipelines

```python
def child_pipeline(data):
    with RunContext("child-pipeline") as run:
        # Process data
        return result

def parent_pipeline(inputs):
    with RunContext("parent-pipeline") as run:
        with StepContext("preprocess", StepType.TRANSFORM) as step:
            processed = preprocess(inputs)

        # Child pipeline creates its own trace
        results = child_pipeline(processed)

        with StepContext("aggregate", StepType.TRANSFORM) as step:
            final = aggregate(results)

        run.set_final_output({"result": final})
```

## Maintenance

### Set Up Retention Policies

```sql
-- Delete runs older than 90 days
DELETE FROM runs
WHERE created_at < NOW() - INTERVAL '90 days'
  AND status = 'SUCCESS';

-- Keep failed runs longer (180 days)
DELETE FROM runs
WHERE created_at < NOW() - INTERVAL '180 days'
  AND status = 'FAILURE';
```

### Archive Old Data

```python
# Export to S3 before deleting
import boto3

runs = db.query(Run).filter(
    Run.created_at < datetime.now() - timedelta(days=90)
).all()

s3 = boto3.client('s3')
for run in runs:
    s3.put_object(
        Bucket='xray-archive',
        Key=f'runs/{run.id}.json',
        Body=json.dumps(run.to_dict())
    )

# Then delete from database
db.delete(runs)
```

### Monitor Database Size

```sql
-- Check table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## Anti-Patterns

### Don't Over-Instrument

**❌ Bad**:
```python
with StepContext("read_config", StepType.CUSTOM):
    config = read_config()  # Too granular!

with StepContext("validate_config", StepType.CUSTOM):
    validate(config)  # Too granular!
```

**✅ Good**:
```python
with StepContext("initialize", StepType.CUSTOM) as step:
    config = read_config()
    validate(config)
    step.set_reasoning("Read and validated configuration")
```

### Don't Store Everything

**❌ Bad**:
```python
# Storing 100MB of data
step.set_outputs({"all_embeddings": giant_array.tolist()})
```

**✅ Good**:
```python
# Store summary
step.set_outputs({
    "embedding_count": len(giant_array),
    "embedding_shape": giant_array.shape,
    "avg_magnitude": np.mean(np.linalg.norm(giant_array, axis=1))
})
```

### Don't Ignore Sampling

**❌ Bad**:
```python
# Forcing full capture for debugging, then forgetting to change back
configure(max_candidates_full_capture=100000)
```

**✅ Good**:
```python
# Use environment variable
configure(
    max_candidates_full_capture=int(os.getenv("XRAY_MAX_CAPTURE", "100"))
)
```

## Summary

**Do**:
- ✅ Use descriptive names
- ✅ Always set reasoning
- ✅ Track candidate counts
- ✅ Use async mode in production
- ✅ Let sampling work
- ✅ Add rich metadata
- ✅ Query across pipelines
- ✅ Test with X-Ray enabled

**Don't**:
- ❌ Use generic names
- ❌ Skip reasoning
- ❌ Disable sampling unnecessarily
- ❌ Log sensitive data
- ❌ Over-instrument
- ❌ Store giant objects
- ❌ Ignore fallback logs

---

**Next Steps**:
- **[Examples](./examples.md)** - See real-world patterns
- **[Configuration](./configuration.md)** - Advanced setup
- **[Troubleshooting](./troubleshooting.md)** - Common issues
