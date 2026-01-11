# X-Ray Usage Example: Complete Workflow

This document shows a **complete real-world example** of how X-Ray is used from integration to debugging.

## Scenario: Production Bug in Competitor Selection API

You're running an e-commerce FastAPI backend. A customer reports:
> "Why is a laptop stand showing as a competitor for my iPhone case?"

Let's see how X-Ray helps you debug this **in 5 minutes**.

---

## Step 1: Your Application (Already Instrumented)

Your FastAPI application has X-Ray integrated:

```python
# app/main.py
from fastapi import FastAPI
from xray import RunContext, StepContext, StepType, configure

configure(
    api_url="http://xray-api.mycompany.com",
    enabled=True,
    async_mode=True
)

app = FastAPI()

@app.post("/api/products/{product_id}/competitors")
async def find_competitors(product_id: str):
    """Find competitor products"""

    # Wrap with X-Ray
    with RunContext(
        "competitor-selection",
        metadata={"product_id": product_id}
    ) as run:

        # Your existing pipeline steps...
        with StepContext("get_product", StepType.CUSTOM) as step:
            product = get_product(product_id)
            step.set_outputs({"title": product.title})

        with StepContext("generate_keywords", StepType.LLM) as step:
            keywords = llm.generate_keywords(product.title)
            step.set_outputs({"keywords": keywords})
            step.set_reasoning("Used GPT-4 to extract keywords")

        with StepContext("search_catalog", StepType.SEARCH) as step:
            candidates = search_catalog(keywords)
            step.set_candidates(candidates)

        with StepContext("filter_by_category", StepType.FILTER) as step:
            threshold = 0.3  # BUG HERE!
            step.set_inputs({"threshold": threshold})
            filtered = filter_by_category(candidates, threshold)
            step.set_candidates(filtered, previous_count=len(candidates))
            step.set_reasoning(f"Filtered with threshold {threshold}")

        with StepContext("rank_by_relevance", StepType.RANK) as step:
            ranked = rank_by_relevance(filtered)
            step.set_candidates(ranked[:10])

        result = ranked[0]
        run.set_final_output({"competitor_asin": result.asin})
        return result

# Your app runs normally!
# When this endpoint is called, X-Ray silently sends trace data
# to the X-Ray API in the background (non-blocking, <1ms overhead)
```

**What happens at runtime:**
- ✅ Customer makes request: `POST /api/products/B09ABC001/competitors`
- ✅ Your API processes normally and returns result
- ✅ In background, X-Ray sends trace to X-Ray API
- ✅ Customer sees response (they don't know X-Ray exists)

**Your application logs:**
```
INFO: 127.0.0.1:12345 - "POST /api/products/B09ABC001/competitors HTTP/1.1" 200 OK
```

**No X-Ray output in terminal!** (unless you set `verbose=True`)

---

## Step 2: Customer Reports Bug

Customer: "I got laptop stand B08XYZ001 as competitor for my iPhone case!"

You need to debug:
- Product ID: `B09ABC001` (iPhone case)
- Wrong competitor returned: `B08XYZ001` (Laptop stand)

---

## Step 3: Query X-Ray API (Find the Run)

Open terminal and query X-Ray API:

```bash
# Find runs for this product
curl "http://xray-api.mycompany.com/api/runs?pipeline_name=competitor-selection&limit=50" \
  | jq '.runs[] | select(.metadata.product_id == "B09ABC001")'
```

**Output:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "pipeline_name": "competitor-selection",
  "status": "SUCCESS",
  "start_time": "2025-01-12T10:32:15Z",
  "end_time": "2025-01-12T10:32:18Z",
  "metadata": {
    "product_id": "B09ABC001"
  },
  "final_output": {
    "competitor_asin": "B08XYZ001"
  }
}
```

Found it! Run ID: `550e8400-e29b-41d4-a716-446655440000`

---

## Step 4: Get Detailed Trace

Query for the full trace with all steps:

```bash
curl "http://xray-api.mycompany.com/api/runs/550e8400-e29b-41d4-a716-446655440000"
```

**Output (formatted for readability):**
```json
{
  "run": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "pipeline_name": "competitor-selection",
    "status": "SUCCESS"
  },
  "steps": [
    {
      "step_name": "get_product",
      "step_type": "CUSTOM",
      "duration_ms": 45,
      "outputs": {
        "title": "iPhone 15 Pro Silicone Case"
      }
    },
    {
      "step_name": "generate_keywords",
      "step_type": "LLM",
      "duration_ms": 1250,
      "outputs": {
        "keywords": ["phone case", "iPhone case", "protective case"]
      },
      "reasoning": "Used GPT-4 to extract keywords"
    },
    {
      "step_name": "search_catalog",
      "step_type": "SEARCH",
      "duration_ms": 320,
      "candidates_in": null,
      "candidates_out": 5000,
      "reasoning": "Searched catalog"
    },
    {
      "step_name": "filter_by_category",
      "step_type": "FILTER",
      "duration_ms": 120,
      "candidates_in": 5000,
      "candidates_out": 4200,
      "inputs": {
        "threshold": 0.3
      },
      "reasoning": "Filtered with threshold 0.3",
      "candidates_data": [
        {"asin": "B08XYZ001", "title": "Laptop Stand", "category": "Computer Accessories"},
        {"asin": "B09ABC002", "title": "iPhone Case", "category": "Phone Accessories"}
      ]
    },
    {
      "step_name": "rank_by_relevance",
      "step_type": "RANK",
      "duration_ms": 180,
      "candidates_in": 4200,
      "candidates_out": 10,
      "candidates_data": [
        {"asin": "B08XYZ001", "title": "Laptop Stand", "score": 0.89},
        {"asin": "B09ABC002", "title": "iPhone Case", "score": 0.75}
      ]
    }
  ]
}
```

---

## Step 5: Analyze & Find Root Cause

Looking at the trace:

### 🔍 Step 3: `filter_by_category`
- **Input**: `threshold: 0.3`
- **Candidates**: `5000 → 4200` (only **16% filtered**)
- **Sample data shows**: Laptop stand (wrong category) passed through!
- **❌ BUG FOUND**: Threshold `0.3` is too low!

### 🔍 Step 4: `rank_by_relevance`
- Laptop stand scored `0.89` (highest)
- iPhone case scored `0.75` (lower)
- **❌ BUG**: Why did laptop stand rank higher?

**Root Cause:**
1. Filter threshold (`0.3`) too low → Let wrong categories through
2. Ranking algorithm boosted laptop stand (maybe due to price similarity)

**Time to find**: **~2 minutes** instead of hours!

---

## Step 6: Fix the Code

Update the threshold:

```python
# app/main.py - Fix the bug
with StepContext("filter_by_category", StepType.FILTER) as step:
    threshold = 0.7  # FIXED: Increased from 0.3
    step.set_inputs({"threshold": threshold})
    filtered = filter_by_category(candidates, threshold)
    step.set_candidates(filtered, previous_count=len(candidates))
    step.set_reasoning(f"Filtered with threshold {threshold}")
```

Deploy the fix.

---

## Step 7: Verify the Fix

Test the same product again:

```bash
# Call your API
curl -X POST "http://api.mycompany.com/api/products/B09ABC001/competitors"

# Query X-Ray API for the new run
curl "http://xray-api.mycompany.com/api/runs?pipeline_name=competitor-selection&limit=1" \
  | jq '.runs[0].id'

# Get trace
curl "http://xray-api.mycompany.com/api/runs/{new_run_id}" \
  | jq '.steps[] | select(.step_name == "filter_by_category")'
```

**New Output:**
```json
{
  "step_name": "filter_by_category",
  "candidates_in": 5000,
  "candidates_out": 500,  // ✅ 90% filtered now!
  "inputs": {
    "threshold": 0.7
  }
}
```

**✅ Fixed!** Now filtering out 90% instead of 16%.

---

## Summary: The Complete Workflow

```
1. Your app runs normally
   • Customer makes request
   • X-Ray silently captures trace (async, non-blocking)
   • Customer gets response

2. Bug reported
   • Customer: "Wrong result for product X"

3. Query X-Ray API (terminal/curl)
   • Find run by product_id
   • Get full trace with all steps

4. Analyze trace
   • See inputs, outputs, candidates at each step
   • Identify which step failed
   • Understand WHY (reasoning + actual data)

5. Fix code
   • Update threshold, algorithm, etc.

6. Verify fix
   • Query X-Ray API for new runs
   • Confirm the issue is resolved

Total time: ~5 minutes instead of hours/days
```

---

## Where Is X-Ray Output Visible?

### ❌ NOT in Your Application Terminal

Your application runs normally:
```
INFO: Started server process [12345]
INFO: Waiting for application startup.
INFO: Application startup complete.
INFO: 127.0.0.1:54321 - "POST /api/products/B09ABC001/competitors" 200 OK
```

No X-Ray output here! (unless `verbose=True`)

### ✅ In X-Ray API Responses

Query the API when you need to debug:

```bash
# List runs
curl http://xray-api.mycompany.com/api/runs

# Get specific run
curl http://xray-api.mycompany.com/api/runs/{run_id}

# Query across pipelines
curl -X POST http://xray-api.mycompany.com/api/steps/query \
  -d '{"step_type": "FILTER", "min_reduction_rate": 0.9}'
```

### ✅ In Custom Scripts

```python
# debug.py
import requests

response = requests.get("http://xray-api.mycompany.com/api/runs/{run_id}")
trace = response.json()

for step in trace["steps"]:
    print(f"{step['step_name']}: {step['candidates_in']} → {step['candidates_out']}")
```

### ✅ In Web Dashboard (Future)

Build a Streamlit/React dashboard that queries the X-Ray API.

---

## Common Questions

### Q: Do I see X-Ray output in my app logs?
**A:** No (unless `verbose=True`). Query the X-Ray API separately when debugging.

### Q: Does X-Ray slow down my app?
**A:** No. <1ms overhead with `async_mode=True` (non-blocking background send).

### Q: What if X-Ray API is down?
**A:** Your app continues normally. Set `fallback_mode=FallbackMode.SILENT` (production) or `LOG` (development).

### Q: How do I view traces?
**A:** Query the X-Ray API via:
- curl/HTTP requests
- Python scripts
- Custom dashboards
- Monitoring tools (Datadog, Grafana)

### Q: Can I search across all pipelines?
**A:** Yes! Use the query endpoints:
```bash
curl -X POST http://xray-api/api/steps/query -d '{"step_type": "LLM", "min_duration_ms": 2000}'
```

---

## Next Steps

- **[Integration Guide](docs/integration-guide.md)** - Detailed integration examples
- **[API Reference](docs/api-reference.md)** - All query endpoints
- **[SDK Reference](docs/sdk-reference.md)** - Complete Python API
