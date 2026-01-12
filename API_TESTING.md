# X-Ray API Testing Guide

Complete guide for testing all X-Ray API endpoints using curl.

## Prerequisites

1. **Start the API server:**
   ```bash
   cd xray-api
   source .venv/bin/activate
   uvicorn app.main:app --reload --port 8001
   ```

2. **Run the demo to generate data:**
   ```bash
   cd xray-sdk/examples
   source ../.venv/bin/activate
   python3 competitor_selection_demo.py
   ```

---

## 1. Health Check

Check if API is running.

```bash
curl http://127.0.0.1:8001/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "service": "xray-api",
  "version": "1.0.0"
}
```

---

## 2. Root Endpoint

Get API information.

```bash
curl http://127.0.0.1:8001/
```

**Expected Response:**
```json
{
  "service": "X-Ray API",
  "version": "1.0.0",
  "description": "Debugging system for non-deterministic pipelines"
}
```

---

## 3. List All Runs

Get all pipeline runs.

```bash
curl http://127.0.0.1:8001/api/runs
```

**With Query Parameters:**
```bash
# Filter by pipeline name
curl "http://127.0.0.1:8001/api/runs?pipeline_name=competitor-selection"

# Limit results
curl "http://127.0.0.1:8001/api/runs?limit=10"

# Filter by status
curl "http://127.0.0.1:8001/api/runs?status=SUCCESS"

# Date range
curl "http://127.0.0.1:8001/api/runs?start_date=2026-01-01&end_date=2026-01-31"

# Multiple filters
curl "http://127.0.0.1:8001/api/runs?pipeline_name=competitor-selection&limit=5&status=SUCCESS"
```

**Expected Response:**
```json
{
  "runs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "pipeline_name": "competitor-selection",
      "pipeline_version": "1.0.0",
      "status": "SUCCESS",
      "start_time": "2026-01-13T10:00:00Z",
      "end_time": "2026-01-13T10:00:03Z",
      "duration_ms": 3000,
      "metadata": {
        "product_title": "iPhone 15 Pro Silicone Case",
        "category": "Cell Phone Accessories"
      }
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

---

## 4. Get Run by ID

Get detailed information about a specific run including all steps.

**First, get a run_id from the list:**
```bash
# Get the first run ID
RUN_ID=$(curl -s http://127.0.0.1:8001/api/runs | jq -r '.runs[0].id')
echo $RUN_ID
```

**Then fetch the run details:**
```bash
curl "http://127.0.0.1:8001/api/runs/$RUN_ID"
```

**Or directly:**
```bash
curl "http://127.0.0.1:8001/api/runs/550e8400-e29b-41d4-a716-446655440000"
```

**Expected Response:**
```json
{
  "run": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "pipeline_name": "competitor-selection",
    "pipeline_version": "1.0.0",
    "status": "SUCCESS",
    "start_time": "2026-01-13T10:00:00Z",
    "end_time": "2026-01-13T10:00:03Z",
    "duration_ms": 3000,
    "metadata": {
      "product_title": "iPhone 15 Pro Silicone Case",
      "category": "Cell Phone Accessories"
    },
    "final_output": {
      "selected_competitor": {
        "asin": "B08XYZ001",
        "title": "Adjustable Aluminum Laptop Stand",
        "score": 0.89
      }
    }
  },
  "steps": [
    {
      "id": "step-uuid-1",
      "run_id": "550e8400-e29b-41d4-a716-446655440000",
      "step_name": "generate_keywords",
      "step_type": "LLM",
      "sequence": 0,
      "start_time": "2026-01-13T10:00:00Z",
      "end_time": "2026-01-13T10:00:01Z",
      "duration_ms": 1000,
      "inputs": {
        "product_title": "iPhone 15 Pro Silicone Case",
        "model": "gpt-4"
      },
      "outputs": {
        "keywords": ["phone case", "iPhone case", "protective case"],
        "keyword_count": 3
      },
      "reasoning": "Used GPT-4 to extract relevant search keywords"
    },
    {
      "id": "step-uuid-2",
      "step_name": "filter_by_category",
      "step_type": "FILTER",
      "sequence": 2,
      "duration_ms": 120,
      "candidates_in": 5000,
      "candidates_out": 4200,
      "inputs": {
        "threshold": 0.3
      },
      "filters": {
        "category_similarity_threshold": 0.3,
        "target_category": "Cell Phone Accessories"
      },
      "reasoning": "Filtered by category similarity using threshold 0.3"
    }
  ]
}
```

---

## 5. Query Steps Across Pipelines

Search for steps matching specific criteria across all pipelines.

**Find all FILTER steps:**
```bash
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{
    "step_type": "FILTER"
  }'
```

**Find FILTER steps with high reduction rate (>90%):**
```bash
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{
    "step_type": "FILTER",
    "min_reduction_rate": 0.9
  }'
```

**Find slow LLM steps (>2 seconds):**
```bash
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{
    "step_type": "LLM",
    "min_duration_ms": 2000
  }'
```

**Find steps with many input candidates:**
```bash
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{
    "min_candidates_in": 1000
  }'
```

**Complex query - Find FILTER steps that didn't filter much:**
```bash
curl -X POST http://127.0.0.1:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{
    "step_type": "FILTER",
    "max_reduction_rate": 0.2,
    "limit": 10
  }'
```

**Expected Response:**
```json
{
  "steps": [
    {
      "id": "step-uuid",
      "run_id": "run-uuid",
      "step_name": "filter_by_category",
      "step_type": "FILTER",
      "duration_ms": 120,
      "candidates_in": 5000,
      "candidates_out": 4200,
      "reduction_rate": 0.16,
      "reasoning": "Filtered by category similarity"
    }
  ],
  "total": 1,
  "limit": 100
}
```

---

## 6. Get Analytics for a Pipeline

Get aggregated statistics for a specific pipeline.

```bash
curl "http://127.0.0.1:8001/api/analytics/pipeline/competitor-selection"
```

**Expected Response:**
```json
{
  "pipeline_name": "competitor-selection",
  "total_runs": 10,
  "success_rate": 0.9,
  "avg_duration_ms": 2800,
  "step_stats": {
    "generate_keywords": {
      "count": 10,
      "avg_duration_ms": 1200,
      "step_type": "LLM"
    },
    "filter_by_category": {
      "count": 10,
      "avg_duration_ms": 120,
      "step_type": "FILTER",
      "avg_reduction_rate": 0.16
    }
  }
}
```

---

## 7. Ingest a Trace (Manual Test)

Manually send a trace to the API.

```bash
curl -X POST http://127.0.0.1:8001/api/runs/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "run": {
      "id": "test-run-123",
      "pipeline_name": "test-pipeline",
      "pipeline_version": "1.0.0",
      "start_time": "2026-01-13T10:00:00Z",
      "end_time": "2026-01-13T10:00:02Z",
      "status": "SUCCESS",
      "metadata": {
        "test": true
      },
      "final_output": {
        "result": "success"
      }
    },
    "steps": [
      {
        "id": "test-step-1",
        "run_id": "test-run-123",
        "step_name": "test_step",
        "step_type": "CUSTOM",
        "sequence": 0,
        "start_time": "2026-01-13T10:00:00Z",
        "end_time": "2026-01-13T10:00:01Z",
        "inputs": {"input": "test"},
        "outputs": {"output": "test"},
        "reasoning": "Test step"
      }
    ]
  }'
```

**Expected Response:**
```json
{
  "run_id": "test-run-123",
  "status": "success",
  "steps_ingested": 1
}
```

---

## Complete Testing Script

Save this as `test_api.sh` and run it:

```bash
#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

API_URL="http://127.0.0.1:8001"

echo -e "${BLUE}=== X-Ray API Testing ===${NC}\n"

# Test 1: Health check
echo -e "${BLUE}1. Testing health endpoint...${NC}"
response=$(curl -s "$API_URL/health")
if echo "$response" | grep -q "healthy"; then
    echo -e "${GREEN}✅ Health check passed${NC}\n"
else
    echo -e "${RED}❌ Health check failed${NC}\n"
    exit 1
fi

# Test 2: Root endpoint
echo -e "${BLUE}2. Testing root endpoint...${NC}"
curl -s "$API_URL/" | jq '.'
echo -e "${GREEN}✅ Root endpoint works${NC}\n"

# Test 3: List runs
echo -e "${BLUE}3. Testing list runs...${NC}"
response=$(curl -s "$API_URL/api/runs")
run_count=$(echo "$response" | jq '.total')
echo "Found $run_count runs"
echo -e "${GREEN}✅ List runs works${NC}\n"

# Test 4: Get specific run (if exists)
if [ "$run_count" -gt 0 ]; then
    echo -e "${BLUE}4. Testing get run by ID...${NC}"
    run_id=$(echo "$response" | jq -r '.runs[0].id')
    echo "Fetching run: $run_id"
    curl -s "$API_URL/api/runs/$run_id" | jq '.run.pipeline_name, .steps | length'
    echo -e "${GREEN}✅ Get run by ID works${NC}\n"
else
    echo -e "${RED}⚠️  No runs found, skipping get run test${NC}\n"
fi

# Test 5: Query steps
echo -e "${BLUE}5. Testing step query...${NC}"
curl -s -X POST "$API_URL/api/steps/query" \
  -H "Content-Type: application/json" \
  -d '{"step_type": "FILTER"}' | jq '.total'
echo -e "${GREEN}✅ Step query works${NC}\n"

# Test 6: Analytics
if [ "$run_count" -gt 0 ]; then
    echo -e "${BLUE}6. Testing analytics...${NC}"
    pipeline_name=$(echo "$response" | jq -r '.runs[0].pipeline_name')
    curl -s "$API_URL/api/analytics/pipeline/$pipeline_name" | jq '.total_runs'
    echo -e "${GREEN}✅ Analytics works${NC}\n"
fi

echo -e "${GREEN}=== All tests completed ===${NC}"
```

**Make it executable and run:**
```bash
chmod +x test_api.sh
./test_api.sh
```

---

## Postman Collection

Import this JSON into Postman:

```json
{
  "info": {
    "name": "X-Ray API",
    "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
  },
  "item": [
    {
      "name": "Health Check",
      "request": {
        "method": "GET",
        "url": "http://127.0.0.1:8001/health"
      }
    },
    {
      "name": "List Runs",
      "request": {
        "method": "GET",
        "url": {
          "raw": "http://127.0.0.1:8001/api/runs?limit=10",
          "query": [
            {"key": "pipeline_name", "value": "competitor-selection", "disabled": true},
            {"key": "limit", "value": "10"}
          ]
        }
      }
    },
    {
      "name": "Get Run by ID",
      "request": {
        "method": "GET",
        "url": "http://127.0.0.1:8001/api/runs/{{run_id}}"
      }
    },
    {
      "name": "Query Steps",
      "request": {
        "method": "POST",
        "header": [{"key": "Content-Type", "value": "application/json"}],
        "body": {
          "mode": "raw",
          "raw": "{\n  \"step_type\": \"FILTER\",\n  \"min_reduction_rate\": 0.9\n}"
        },
        "url": "http://127.0.0.1:8001/api/steps/query"
      }
    },
    {
      "name": "Get Analytics",
      "request": {
        "method": "GET",
        "url": "http://127.0.0.1:8001/api/analytics/pipeline/competitor-selection"
      }
    }
  ]
}
```

---

## Debugging Tips

**If no data is returned:**
1. Run the demo: `cd xray-sdk/examples && python3 competitor_selection_demo.py`
2. Wait 2 seconds for async trace to be sent
3. Check API logs for errors

**If API is not responding:**
1. Check if it's running: `curl http://127.0.0.1:8001/health`
2. Check the port: API runs on 8001 by default
3. Check API logs in terminal

**If data looks wrong:**
1. Check the demo output for run_id
2. Query by run_id: `curl http://127.0.0.1:8001/api/runs/{run_id}`
3. Check database: `psql xray_db -c "SELECT id, pipeline_name FROM runs;"`

---

## Next Steps

- See [docs/api-reference.md](docs/api-reference.md) for complete API documentation
- See [USAGE_EXAMPLE.md](USAGE_EXAMPLE.md) for real-world debugging workflow
- See [docs/integration-guide.md](docs/integration-guide.md) for integration examples
