# Integration Guide: Using X-Ray in Your Application

This guide shows how to integrate X-Ray into your existing application and how to actually use it to debug issues.

## The Complete Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Your Application (FastAPI server, cron job, etc.)           │
│    - Instrumented with X-Ray SDK                                │
│    - Runs normally, serves requests                             │
│    - Sends traces to X-Ray API in background (non-blocking)     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ HTTP POST (async, non-blocking)
                         │ Trace data sent here
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. X-Ray API (separate service)                                │
│    - Receives traces                                            │
│    - Stores in PostgreSQL                                       │
│    - Provides query endpoints                                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ When you need to debug:
                         │ Query via API or Web UI
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. You (Developer/Operator)                                     │
│    - Query X-Ray API when issues occur                         │
│    - View traces via curl, Postman, or custom dashboard        │
│    - Analyze decision flow, find root cause                     │
└─────────────────────────────────────────────────────────────────┘
```

## Real-World Integration Example

### Scenario: You Have a FastAPI E-commerce Backend

You have a FastAPI server with multiple routes:

```python
# your_app/main.py (BEFORE X-Ray)
from fastapi import FastAPI

app = FastAPI()

@app.post("/api/products/{product_id}/find-competitors")
async def find_competitors(product_id: str):
    # Your existing complex pipeline
    product = get_product(product_id)
    keywords = generate_keywords(product)
    candidates = search_catalog(keywords)
    filtered = filter_by_category(candidates)
    ranked = rank_by_relevance(filtered)
    return ranked[0]
```

**Problem**: When this returns wrong results, you have no visibility into WHY.

### Step 1: Integrate X-Ray SDK (5 minutes)

```python
# your_app/main.py (AFTER X-Ray integration)
from fastapi import FastAPI
from xray import RunContext, StepType, configure

# Configure X-Ray once at startup
configure(
    api_url="http://xray-api.yourcompany.com",  # Your X-Ray API instance
    enabled=True,
    async_mode=True,  # Non-blocking!
    fallback_mode=FallbackMode.SILENT  # Continue if X-Ray is down
)

app = FastAPI()

@app.post("/api/products/{product_id}/find-competitors")
async def find_competitors(product_id: str):
    # Wrap your pipeline with X-Ray
    with RunContext(
        "competitor-selection",
        metadata={"product_id": product_id, "user_id": request.state.user_id}
    ) as run:

        # Step 1: Get product
        with run.step("get_product", StepType.CUSTOM) as step:
            product = get_product(product_id)
            step.set_outputs({"title": product.title, "category": product.category})

        # Step 2: Generate keywords (LLM)
        with run.step("generate_keywords", StepType.LLM) as step:
            step.set_inputs({"product_title": product.title})
            keywords = generate_keywords(product)
            step.set_outputs({"keywords": keywords})
            step.set_reasoning(f"Used GPT-4 to extract {len(keywords)} keywords")

        # Step 3: Search
        with run.step("search_catalog", StepType.SEARCH) as step:
            candidates = search_catalog(keywords)
            step.set_candidates(
                candidates_in=0,
                candidates_out=len(candidates),
                data=candidates
            )  # Auto-sampled if >100
            step.set_reasoning("Searched via Elasticsearch")

        # Step 4: Filter
        with run.step("filter_by_category", StepType.FILTER) as step:
            threshold = 0.7
            step.set_inputs({"threshold": threshold})
            filtered = filter_by_category(candidates, threshold)
            step.set_candidates(
                candidates_in=len(candidates),
                candidates_out=len(filtered),
                data=filtered
            )
            step.set_reasoning(f"Filtered by category similarity >= {threshold}")

        # Step 5: Rank
        with run.step("rank_by_relevance", StepType.RANK) as step:
            ranked = rank_by_relevance(filtered)
            step.set_candidates(
                candidates_in=len(filtered),
                candidates_out=len(ranked),
                data=ranked[:10]
            )  # Top 10
            step.set_reasoning("Ranked by relevance score")

        result = ranked[0]
        run.set_final_output({"competitor_asin": result.asin, "score": result.score})
        return result
```

**What happens at runtime:**
- ✅ Your API responds normally (no visible change to users)
- ✅ X-Ray sends trace data to X-Ray API **asynchronously** (0.25ms overhead)
- ✅ If X-Ray API is down, your API still works (fallback mode)
- ✅ No output in terminal unless you enable `verbose=True`

### Step 2: Deploy X-Ray API (One-Time Setup)

Deploy X-Ray API as a separate service:

```bash
# On your server or Kubernetes cluster
docker run -d \
  -p 8001:8001 \
  -e DATABASE_URL=postgresql://... \
  xray-api:latest
```

Or deploy to cloud (AWS ECS, GCP Cloud Run, etc.)

**Important**: This is a **separate service** from your main application!

### Step 3: When Issues Occur - Debug via X-Ray API

Now, when you get a bug report: "Product X returned wrong competitor Y"

#### Option A: Query via Terminal (curl)

```bash
# 1. Find the problematic run
curl "http://xray-api.yourcompany.com/api/runs?pipeline_name=competitor-selection&limit=20" \
  | jq '.runs[] | select(.metadata.product_id == "B08XYZ123")'

# Output:
# {
#   "id": "550e8400-e29b-41d4-a716-446655440000",
#   "pipeline_name": "competitor-selection",
#   "status": "SUCCESS",
#   "start_time": "2025-01-12T10:00:00Z",
#   "metadata": {
#     "product_id": "B08XYZ123",
#     "user_id": "user_456"
#   }
# }

# 2. Get detailed trace
curl "http://xray-api.yourcompany.com/api/runs/550e8400-e29b-41d4-a716-446655440000" \
  | jq '.steps[] | {step_name, duration_ms, candidates_in, candidates_out, reasoning}'

# Output shows you EACH STEP:
# {
#   "step_name": "filter_by_category",
#   "duration_ms": 120,
#   "candidates_in": 5000,
#   "candidates_out": 4200,  # ← Only 16% filtered! Bug!
#   "reasoning": "Filtered by category similarity >= 0.3"
# }
```

#### Option B: Query via Python Script

Create a debugging script:

```python
# debug.py
import requests

def debug_product_issue(product_id):
    # Find runs for this product
    response = requests.get(
        "http://xray-api.yourcompany.com/api/runs",
        params={"pipeline_name": "competitor-selection"}
    )

    runs = [r for r in response.json()["runs"]
            if r["metadata"].get("product_id") == product_id]

    if not runs:
        print(f"No runs found for product {product_id}")
        return

    # Get latest run
    run_id = runs[0]["id"]

    # Get detailed trace
    response = requests.get(f"http://xray-api.yourcompany.com/api/runs/{run_id}")
    data = response.json()

    print(f"Debugging run: {run_id}")
    print(f"Status: {data['run']['status']}")
    print(f"\nSteps:")

    for step in data["steps"]:
        print(f"\n  {step['step_name']}:")
        print(f"    Duration: {step['duration_ms']}ms")

        if step['candidates_in'] and step['candidates_out']:
            reduction = (1 - step['candidates_out'] / step['candidates_in']) * 100
            print(f"    Candidates: {step['candidates_in']} → {step['candidates_out']} ({reduction:.1f}% filtered)")

        print(f"    Reasoning: {step['reasoning']}")

        # Check for issues
        if step['step_type'] == 'FILTER' and reduction < 50:
            print(f"    ⚠️  WARNING: Filter not aggressive enough!")

        if step['duration_ms'] > 2000:
            print(f"    ⚠️  WARNING: Slow step!")

# Usage
debug_product_issue("B08XYZ123")
```

Run it:
```bash
python debug.py

# Output:
# Debugging run: 550e8400-e29b-41d4-a716-446655440000
# Status: SUCCESS
#
# Steps:
#
#   filter_by_category:
#     Duration: 120ms
#     Candidates: 5000 → 4200 (16.0% filtered)
#     Reasoning: Filtered by category similarity >= 0.3
#     ⚠️  WARNING: Filter not aggressive enough!
```

#### Option C: Build a Web Dashboard (Future)

Create a simple dashboard:

```python
# dashboard.py (using Streamlit)
import streamlit as st
import requests

st.title("X-Ray Dashboard")

pipeline = st.selectbox("Pipeline", ["competitor-selection", "fraud-detection"])

# Fetch recent runs
response = requests.get(
    "http://xray-api.yourcompany.com/api/runs",
    params={"pipeline_name": pipeline, "limit": 50}
)

runs = response.json()["runs"]

# Show table
st.dataframe(runs)

# Select a run
run_id = st.selectbox("Select Run", [r["id"] for r in runs])

# Show detailed trace
if st.button("Analyze"):
    response = requests.get(f"http://xray-api.yourcompany.com/api/runs/{run_id}")
    data = response.json()

    # Visualize steps
    for step in data["steps"]:
        st.subheader(step["step_name"])
        st.write(f"Duration: {step['duration_ms']}ms")
        st.write(f"Reasoning: {step['reasoning']}")

        if step['candidates_data']:
            st.write("Sample candidates:")
            st.json(step['candidates_data'][:5])
```

Run it:
```bash
streamlit run dashboard.py
# Opens browser at http://localhost:8501
```

## Key Points: Where Is Output Visible?

### ❌ NOT Visible in Your Application's Terminal

X-Ray does **NOT** print anything to your application's stdout/terminal (unless you enable `verbose=True` for debugging).

Your application logs look normal:
```
INFO:     127.0.0.1:54321 - "POST /api/products/B08XYZ123/find-competitors HTTP/1.1" 200 OK
```

### ✅ Visible via X-Ray API Queries

You query the X-Ray API separately:

1. **Via curl/HTTP requests** - Query whenever you need to debug
2. **Via Python scripts** - Automated debugging/alerting
3. **Via Web UI** - Build a dashboard (future enhancement)
4. **Via Monitoring Tools** - Integrate with Datadog, Grafana, etc.

## Common Usage Patterns

### Pattern 1: Debugging Production Issues

**Situation**: User reports wrong result

**Steps**:
1. Get run ID from logs or query by metadata (user_id, product_id, etc.)
2. Query X-Ray API for that run: `curl http://xray-api/api/runs/{run_id}`
3. Analyze steps to find root cause
4. Fix code, deploy
5. Verify fix by querying new runs

### Pattern 2: Finding Patterns Across All Pipelines

**Situation**: Many LLM steps are slow

**Steps**:
```bash
# Find all slow LLM steps across ALL pipelines
curl -X POST http://xray-api/api/steps/query \
  -d '{"step_type": "LLM", "min_duration_ms": 3000}' \
  | jq '.steps[] | {pipeline: .run_id, step: .step_name, duration: .duration_ms}'
```

### Pattern 3: Monitoring & Alerting

**Situation**: Want to be notified of issues automatically

**Setup a cron job**:
```python
# alert.py - runs every hour
import requests
from datetime import datetime, timedelta

# Get analytics for last hour
response = requests.get(
    "http://xray-api/api/analytics/summary",
    params={"pipeline_name": "competitor-selection"}
)

data = response.json()

# Alert if success rate drops
if data["runs"]["success_rate"] < 0.9:
    send_slack_alert(f"⚠️ Success rate dropped to {data['runs']['success_rate']}")

# Alert if pipeline is slow
if data["performance"]["p95_duration_ms"] > 10000:
    send_slack_alert(f"⚠️ P95 latency: {data['performance']['p95_duration_ms']}ms")
```

### Pattern 4: A/B Testing Analysis

**Situation**: Testing two different algorithms

**Code**:
```python
# Variant A
with RunContext("competitor-selection", metadata={"variant": "threshold_0.3"}):
    filtered = filter_by_category(candidates, threshold=0.3)

# Variant B
with RunContext("competitor-selection", metadata={"variant": "threshold_0.7"}):
    filtered = filter_by_category(candidates, threshold=0.7)
```

**Query**:
```bash
# Compare variants
curl http://xray-api/api/runs?pipeline_name=competitor-selection \
  | jq 'group_by(.metadata.variant) |
        map({variant: .[0].metadata.variant,
             avg_duration: (map(.duration_ms) | add / length)})'
```

## Summary: The User Experience

### For Your Application's End Users:
- ✅ **No change** - They don't see or interact with X-Ray
- ✅ **No performance impact** - <1ms overhead (async mode)
- ✅ **Reliability** - App works even if X-Ray is down

### For You (Developer/Operator):
- ✅ **Query when needed** - No constant output
- ✅ **Debug efficiently** - Find root cause in minutes instead of hours
- ✅ **Proactive monitoring** - Query API to detect patterns
- ✅ **Build custom tools** - Dashboard, alerts, integrations

### Typical Workflow:

```
1. Integrate X-Ray SDK (one-time, 30 min)
   ↓
2. Deploy X-Ray API (one-time, 30 min)
   ↓
3. Application runs normally (traces sent in background)
   ↓
4. When bug occurs:
   - Query X-Ray API
   - Analyze trace
   - Find root cause
   - Fix code
   ↓
5. Verify fix by querying new traces
```

## Next Steps

- **[API Reference](./api-reference.md)** - All query endpoints
- **[Best Practices](./best-practices.md)** - Production tips
- **[Examples](../examples/)** - See real debugging workflow
