# Getting Started with X-Ray

## What is X-Ray?

X-Ray is a debugging system for multi-step pipelines that helps you understand **why** your system made specific decisions, not just what happened.

**Perfect for**:
- AI/LLM-powered pipelines
- Multi-step selection algorithms
- Recommendation systems
- Search and ranking pipelines
- Any non-deterministic process

## Installation

### Prerequisites

- Python 3.10 or higher
- PostgreSQL 12 or higher

### Install the SDK

```bash
pip install xray-sdk
```

Or with Poetry:
```bash
poetry add xray-sdk
```

### Install the API (Optional)

If you want to run your own X-Ray API server:

```bash
# Clone the repository
git clone https://github.com/your-org/xray-api
cd xray-api

# Install dependencies
poetry install

# Set up database
createdb xray_db

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## Your First X-Ray Pipeline

### Step 1: Configure the SDK

```python
from xray import configure

configure(
    api_url="http://localhost:8001",
    enabled=True
)
```

### Step 2: Instrument Your Pipeline

```python
from xray import RunContext, StepType

def find_best_product(query: str):
    # Wrap your pipeline in a RunContext
    with RunContext("product-search") as run:

        # Wrap each step using run.step()
        with run.step("search", StepType.SEARCH) as step:
            results = search_database(query)
            step.set_candidates(
                candidates_in=0,
                candidates_out=len(results),
                data=results
            )
            step.set_reasoning("Searched product database")

        with run.step("filter", StepType.FILTER) as step:
            filtered = filter_by_price(results, min_price=10, max_price=100)
            step.set_candidates(
                candidates_in=len(results),
                candidates_out=len(filtered),
                data=filtered
            )
            step.set_reasoning("Filtered by price range $10-$100")

        with run.step("rank", StepType.RANK) as step:
            ranked = rank_by_relevance(filtered, query)
            step.set_candidates(
                candidates_in=len(filtered),
                candidates_out=len(ranked),
                data=ranked
            )
            step.set_reasoning("Ranked by relevance score")

        best = ranked[0]
        run.set_final_output({"product": best})
        return best
```

### Step 3: Run Your Pipeline

```python
product = find_best_product("wireless headphones")
print(f"Selected: {product}")
```

That's it! X-Ray automatically:
- ✅ Captures timing for each step
- ✅ Tracks candidate counts
- ✅ Samples large datasets (5000→150)
- ✅ Sends data to the API (async, non-blocking)

### Step 4: Query Your Data

```bash
# Get all runs
curl http://localhost:8001/api/runs?pipeline_name=product-search

# Get detailed trace for a specific run
curl http://localhost:8001/api/runs/{run_id}

# Find all filter steps with high reduction
curl -X POST http://localhost:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"step_type": "FILTER", "min_reduction_rate": 0.9}'
```

## What Gets Captured?

For each **Run**:
- Pipeline name and version
- Start and end time
- Success/failure status
- Custom metadata
- Final output

For each **Step**:
- Step name and type
- Start and end time
- Input parameters
- Output results
- Reasoning (why this decision)
- Candidate counts (how many in/out)
- Sampled candidates (actual data)
- Filters applied
- Custom metadata

## Next Steps

- **[SDK Reference](./sdk-reference.md)** - Complete API documentation
- **[API Reference](./api-reference.md)** - All endpoints
- **[Configuration](./configuration.md)** - Advanced setup
- **[Best Practices](./best-practices.md)** - Tips and patterns
- **[Examples](./examples.md)** - Real-world use cases

## Quick Tips

### Minimal Instrumentation

Don't want to instrument every step? Just wrap the whole pipeline:

```python
with RunContext("my-pipeline") as run:
    # Your existing code - unchanged
    result = do_complex_work()

    # Just add final output
    run.set_final_output({"result": result})
```

You get: Start/end time, status, final output. No per-step visibility, but still useful!

### Disable in Production

```python
import os

configure(
    enabled=os.getenv("XRAY_ENABLED", "false") == "true"
)
```

Set `XRAY_ENABLED=true` only when debugging.

### Handle API Downtime

```python
from xray import configure, FallbackMode

configure(
    fallback_mode=FallbackMode.SILENT  # Continue silently if API is down
)
```

Your pipeline never fails due to X-Ray!

## Common Issues

### "Connection refused"

**Problem**: Can't connect to X-Ray API

**Solution**: Check if the API is running:
```bash
curl http://localhost:8001/health
```

If not, start it:
```bash
cd xray-api
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### "Import error"

**Problem**: `ModuleNotFoundError: No module named 'xray'`

**Solution**: Install the SDK:
```bash
pip install xray-sdk
```

### "Too much data"

**Problem**: Steps with 10,000+ candidates are slow

**Solution**: X-Ray automatically samples! If you want more control:
```python
configure(
    max_candidates_full_capture=50  # Only store full data for <50 candidates
)
```

## Get Help

- **Documentation**: See other docs in this folder
- **Examples**: Check the `examples/` directory
- **Issues**: Report bugs on GitHub
- **Questions**: Ask in Discussions

---

**Ready to dive deeper?** Check out the [SDK Reference](./sdk-reference.md) for complete API documentation.
