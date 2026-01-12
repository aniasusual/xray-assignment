# Quick API Reference - Curl Commands

One-page reference for all X-Ray API endpoints.

## Prerequisites
```bash
# Start API
cd xray-api && source .venv/bin/activate && uvicorn app.main:app --reload --port 8001

# Run demo to generate data
cd xray-sdk/examples && source ../.venv/bin/activate && python3 competitor_selection_demo.py
```

---

## 1. Health & Info

```bash
# Health check
curl http://127.0.0.1:8001/health

# Root info
curl http://127.0.0.1:8001/
```

---

## 2. List Runs

```bash
# All runs
curl http://127.0.0.1:8001/api/runs

# Filter by pipeline
curl "http://127.0.0.1:8001/api/runs?pipeline_name=competitor-selection"

# Limit results
curl "http://127.0.0.1:8001/api/runs?limit=5"

# By status
curl "http://127.0.0.1:8001/api/runs?status=SUCCESS"

# Date range
curl "http://127.0.0.1:8001/api/runs?start_date=2026-01-01&end_date=2026-01-31"
```

---

## 3. Get Run Details

```bash
# Get first run ID
RUN_ID=$(curl -s http://127.0.0.1:8001/api/runs | jq -r '.runs[0].id')

# Get run with all steps
curl "http://127.0.0.1:8001/api/runs/$RUN_ID"

# Pretty print with jq
curl -s "http://127.0.0.1:8001/api/runs/$RUN_ID" | jq '.'
```

---

## 4. Query Steps

```bash
# All FILTER steps
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"step_type": "FILTER"}'

# FILTER steps with >90% reduction
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"step_type": "FILTER", "min_reduction_rate": 0.9}'

# FILTER steps with <20% reduction (problematic!)
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"step_type": "FILTER", "max_reduction_rate": 0.2}'

# Slow LLM steps (>2s)
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"step_type": "LLM", "min_duration_ms": 2000}'

# Steps with many candidates
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"min_candidates_in": 1000}'
```

---

## 5. Analytics

```bash
# Get pipeline analytics
curl "http://127.0.0.1:8001/api/analytics/pipeline/competitor-selection"

# Pretty print
curl -s "http://127.0.0.1:8001/api/analytics/pipeline/competitor-selection" | jq '.'
```

---

## 6. Common Debugging Queries

```bash
# Find the latest run
curl -s "http://127.0.0.1:8001/api/runs?limit=1" | jq '.runs[0]'

# Find runs that failed
curl "http://127.0.0.1:8001/api/runs?status=FAILURE"

# Find inefficient filters (not filtering enough)
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"step_type": "FILTER", "max_reduction_rate": 0.3}'

# Find all steps in a specific run
RUN_ID="your-run-id-here"
curl -s "http://127.0.0.1:8001/api/runs/$RUN_ID" | jq '.steps'

# Count total runs
curl -s "http://127.0.0.1:8001/api/runs" | jq '.total'

# Get pipeline names
curl -s "http://127.0.0.1:8001/api/runs" | jq '.runs[].pipeline_name' | sort | uniq
```

---

## 7. Testing Script

```bash
# Save as test.sh
#!/bin/bash
API="http://127.0.0.1:8001"

echo "1. Health check..."
curl -s $API/health | jq '.'

echo -e "\n2. List runs..."
curl -s $API/api/runs | jq '.total, .runs[0].id'

echo -e "\n3. Get latest run..."
RUN_ID=$(curl -s $API/api/runs | jq -r '.runs[0].id')
curl -s "$API/api/runs/$RUN_ID" | jq '.run.pipeline_name, .steps | length'

echo -e "\n4. Query problematic filters..."
curl -s -X POST $API/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"step_type": "FILTER", "max_reduction_rate": 0.2}' | jq '.total'

echo -e "\n5. Analytics..."
curl -s "$API/api/analytics/pipeline/competitor-selection" | jq '.total_runs, .success_rate'

echo -e "\n✅ All tests complete"
```

---

## 8. Response Examples

**List Runs Response:**
```json
{
  "runs": [{"id": "...", "pipeline_name": "...", "status": "SUCCESS"}],
  "total": 10,
  "limit": 100,
  "offset": 0
}
```

**Run Details Response:**
```json
{
  "run": {
    "id": "...",
    "pipeline_name": "competitor-selection",
    "status": "SUCCESS",
    "duration_ms": 3000,
    "metadata": {...},
    "final_output": {...}
  },
  "steps": [
    {
      "step_name": "filter_by_category",
      "step_type": "FILTER",
      "candidates_in": 5000,
      "candidates_out": 4200,
      "reasoning": "..."
    }
  ]
}
```

**Step Query Response:**
```json
{
  "steps": [
    {
      "step_name": "...",
      "step_type": "FILTER",
      "candidates_in": 5000,
      "candidates_out": 4200,
      "reduction_rate": 0.16
    }
  ],
  "total": 5
}
```

---

## See Also

- [API_TESTING.md](API_TESTING.md) - Complete testing guide
- [docs/api-reference.md](docs/api-reference.md) - Full API documentation
- [USAGE_EXAMPLE.md](USAGE_EXAMPLE.md) - Real-world debugging workflow
