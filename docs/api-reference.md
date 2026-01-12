# API Reference

Complete reference for the X-Ray REST API.

> **Quick Testing**: See [../API_TESTING.md](../API_TESTING.md) for ready-to-use curl commands and a complete testing script.

## Base URL

```
http://localhost:8001
```

Replace with your deployed API URL in production.

## Authentication

Currently no authentication. Add API keys for production deployment.

## Endpoints

### Health Check

Check if the API is running.

```http
GET /health
```

**Response** (200 OK):
```json
{
  "status": "healthy",
  "service": "xray-api",
  "version": "1.0.0"
}
```

**Example**:
```bash
curl http://localhost:8001/health
```

---

### Ingest Trace

Store a complete pipeline run with all steps.

```http
POST /api/runs/ingest
Content-Type: application/json
```

**Request Body**:
```json
{
  "run": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "pipeline_name": "competitor-selection",
    "pipeline_version": "1.0.0",
    "start_time": "2025-01-12T10:00:00Z",
    "end_time": "2025-01-12T10:00:05Z",
    "status": "SUCCESS",
    "metadata": {
      "user_id": "123",
      "environment": "production"
    },
    "final_output": {
      "selected_competitor": "B08XYZ123"
    }
  },
  "steps": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "step_name": "generate_keywords",
      "step_type": "LLM",
      "sequence": 0,
      "start_time": "2025-01-12T10:00:00Z",
      "end_time": "2025-01-12T10:00:01.250Z",
      "inputs": {
        "product_title": "iPhone 15 Pro Case"
      },
      "outputs": {
        "keywords": ["phone case", "iPhone case"]
      },
      "reasoning": "Used GPT-4 to extract keywords",
      "candidates_in": null,
      "candidates_out": null,
      "candidates_data": null,
      "filters_applied": {},
      "metadata": {}
    }
  ]
}
```

**Response** (201 Created):
```json
{
  "success": true,
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Trace ingested successfully",
  "steps_count": 5
}
```

**Error** (400 Bad Request):
```json
{
  "detail": "Invalid payload: missing required field 'pipeline_name'"
}
```

**Example**:
```bash
curl -X POST http://localhost:8001/api/runs/ingest \
  -H "Content-Type: application/json" \
  -d @trace.json
```

---

### List Runs

Get a list of pipeline runs with optional filtering.

```http
GET /api/runs?pipeline_name={name}&status={status}&limit={limit}&offset={offset}
```

**Query Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `pipeline_name` | string | No | - | Filter by pipeline |
| `status` | string | No | - | Filter by status (SUCCESS, FAILURE, etc.) |
| `limit` | integer | No | 50 | Results per page (max 1000) |
| `offset` | integer | No | 0 | Pagination offset |

**Response** (200 OK):
```json
{
  "runs": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "pipeline_name": "competitor-selection",
      "pipeline_version": "1.0.0",
      "start_time": "2025-01-12T10:00:00Z",
      "end_time": "2025-01-12T10:00:05Z",
      "status": "SUCCESS",
      "metadata": {
        "user_id": "123"
      },
      "final_output": {
        "selected_competitor": "B08XYZ123"
      }
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 50
}
```

**Examples**:
```bash
# Get all runs
curl http://localhost:8001/api/runs

# Filter by pipeline
curl http://localhost:8001/api/runs?pipeline_name=competitor-selection

# Filter by status
curl http://localhost:8001/api/runs?status=FAILURE

# Pagination
curl http://localhost:8001/api/runs?limit=10&offset=20
```

---

### Get Run Details

Get a specific run with all its steps.

```http
GET /api/runs/{run_id}
```

**Path Parameters**:
- `run_id` (UUID): Run identifier

**Response** (200 OK):
```json
{
  "run": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "pipeline_name": "competitor-selection",
    "pipeline_version": "1.0.0",
    "start_time": "2025-01-12T10:00:00Z",
    "end_time": "2025-01-12T10:00:05Z",
    "status": "SUCCESS",
    "metadata": {},
    "final_output": {}
  },
  "steps": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "run_id": "550e8400-e29b-41d4-a716-446655440000",
      "step_name": "generate_keywords",
      "step_type": "LLM",
      "sequence": 0,
      "start_time": "2025-01-12T10:00:00Z",
      "end_time": "2025-01-12T10:00:01.250Z",
      "duration_ms": 1250,
      "inputs": {},
      "outputs": {},
      "reasoning": "Used GPT-4 to extract keywords",
      "candidates_in": null,
      "candidates_out": null,
      "reduction_rate": null,
      "candidates_data": null,
      "filters_applied": {},
      "metadata": {}
    }
  ]
}
```

**Error** (404 Not Found):
```json
{
  "detail": "Run 550e8400-e29b-41d4-a716-446655440000 not found"
}
```

**Example**:
```bash
curl http://localhost:8001/api/runs/550e8400-e29b-41d4-a716-446655440000
```

---

### Query Steps (Cross-Pipeline)

Query steps across all pipelines with flexible filtering.

```http
POST /api/steps/query
Content-Type: application/json
```

**Request Body**:
```json
{
  "pipeline_name": "competitor-selection",
  "step_name": "filter_by_category",
  "step_type": "FILTER",
  "min_reduction_rate": 0.9,
  "max_reduction_rate": 1.0,
  "min_duration_ms": 100,
  "max_duration_ms": 5000
}
```

**All fields are optional**. Mix and match to build your query.

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `pipeline_name` | string | Filter by pipeline |
| `step_name` | string | Filter by step name |
| `step_type` | string | Filter by type (LLM, SEARCH, FILTER, etc.) |
| `min_reduction_rate` | float | Min reduction (0.0-1.0) |
| `max_reduction_rate` | float | Max reduction (0.0-1.0) |
| `min_duration_ms` | float | Min duration in milliseconds |
| `max_duration_ms` | float | Max duration in milliseconds |

**Query Parameters**:
- `limit` (int): Results per page (default 50)
- `offset` (int): Pagination offset (default 0)

**Response** (200 OK):
```json
{
  "steps": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "run_id": "550e8400-e29b-41d4-a716-446655440000",
      "step_name": "filter_by_category",
      "step_type": "FILTER",
      "sequence": 2,
      "duration_ms": 120,
      "candidates_in": 5000,
      "candidates_out": 500,
      "reduction_rate": 0.9,
      "filters_applied": {
        "category_similarity_threshold": 0.7
      },
      "reasoning": "Filtered by category similarity"
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 50
}
```

**Examples**:
```bash
# Find all FILTER steps with high reduction
curl -X POST http://localhost:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"step_type": "FILTER", "min_reduction_rate": 0.9}'

# Find slow LLM steps
curl -X POST http://localhost:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"step_type": "LLM", "min_duration_ms": 2000}'

# Find specific step across all runs
curl -X POST http://localhost:8001/api/steps/query \
  -H "Content-Type: application/json" \
  -d '{"step_name": "filter_by_price"}'
```

---

### Analytics Summary

Get aggregated metrics for a pipeline.

```http
GET /api/analytics/summary?pipeline_name={name}&days={days}
```

**Query Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `pipeline_name` | string | No | - | Filter by pipeline |
| `days` | integer | No | 30 | Time window in days |

**Response** (200 OK):
```json
{
  "pipeline_name": "competitor-selection",
  "date_range": {
    "start": "2024-12-13",
    "end": "2025-01-12"
  },
  "runs": {
    "total": 1523,
    "successful": 1450,
    "failed": 73,
    "success_rate": 0.952
  },
  "performance": {
    "avg_duration_ms": 4250,
    "p50_duration_ms": 4100,
    "p95_duration_ms": 6800,
    "p99_duration_ms": 9200
  },
  "steps": {
    "avg_steps_per_run": 5.2,
    "slowest_step": "llm_validate",
    "slowest_step_avg_ms": 2100
  }
}
```

**Example**:
```bash
# Last 30 days
curl http://localhost:8001/api/analytics/summary?pipeline_name=competitor-selection

# Last 7 days
curl http://localhost:8001/api/analytics/summary?pipeline_name=competitor-selection&days=7
```

---

### Analytics by Step Type

Get metrics grouped by step type.

```http
GET /api/analytics/by-step-type?pipeline_name={name}
```

**Query Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `pipeline_name` | string | No | - | Filter by pipeline |

**Response** (200 OK):
```json
{
  "step_types": [
    {
      "step_type": "LLM",
      "count": 3045,
      "avg_duration_ms": 1850,
      "p95_duration_ms": 3200
    },
    {
      "step_type": "FILTER",
      "count": 1523,
      "avg_duration_ms": 120,
      "avg_reduction_rate": 0.72,
      "p95_reduction_rate": 0.95
    },
    {
      "step_type": "RANK",
      "count": 1523,
      "avg_duration_ms": 2100,
      "avg_reduction_rate": 0.95
    }
  ]
}
```

**Example**:
```bash
curl http://localhost:8001/api/analytics/by-step-type?pipeline_name=competitor-selection
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": "Error message here"
}
```

**Status Codes**:
- `200 OK` - Success
- `201 Created` - Resource created
- `400 Bad Request` - Invalid input
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server error

---

## Interactive Documentation

The API provides auto-generated interactive docs:

- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

These allow you to:
- Browse all endpoints
- Test requests directly
- See request/response schemas
- Copy curl commands

---

## Rate Limiting

Currently no rate limiting. Implement for production:

```python
# In production, add:
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.get("/api/runs")
@limiter.limit("100/minute")
async def list_runs():
    pass
```

---

## Pagination

All list endpoints support pagination:

```bash
# Page 1 (results 0-49)
curl http://localhost:8001/api/runs?limit=50&offset=0

# Page 2 (results 50-99)
curl http://localhost:8001/api/runs?limit=50&offset=50

# Page 3 (results 100-149)
curl http://localhost:8001/api/runs?limit=50&offset=100
```

**Max limit**: 1000 results per request

---

## Common Queries

### Find Bottlenecks

```bash
# Find slowest steps
curl -X POST http://localhost:8001/api/steps/query \
  -d '{"min_duration_ms": 5000}'
```

### Find Inefficient Filters

```bash
# Find filters with low reduction
curl -X POST http://localhost:8001/api/steps/query \
  -d '{"step_type": "FILTER", "max_reduction_rate": 0.3}'
```

### Find Failed Runs

```bash
curl http://localhost:8001/api/runs?status=FAILURE
```

### Compare Pipelines

```bash
# Get analytics for each pipeline
curl http://localhost:8001/api/analytics/summary?pipeline_name=pipeline-a
curl http://localhost:8001/api/analytics/summary?pipeline_name=pipeline-b
```

---

## Client Libraries

### Python

Use the built-in SDK client:

```python
from xray.client import XRayClient

client = XRayClient(api_url="http://localhost:8001")

# Get run
run = client.get_run(run_id)

# Query steps
steps = client.query_steps(step_type="FILTER", min_reduction_rate=0.9)
```

### JavaScript

```javascript
// Example with fetch
const response = await fetch('http://localhost:8001/api/runs');
const data = await response.json();
console.log(data.runs);
```

### cURL

All examples in this doc use cURL. Copy-paste them!

---

## Deployment

### Environment Variables

```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/xray_db"
export API_HOST="0.0.0.0"
export API_PORT="8001"
export CORS_ORIGINS="https://app.yourcompany.com"
```

### Docker

```dockerfile
FROM python:3.10
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Production Checklist

- [ ] Add authentication (API keys)
- [ ] Enable HTTPS
- [ ] Set up rate limiting
- [ ] Configure CORS properly
- [ ] Add monitoring (Datadog, New Relic)
- [ ] Set up database backups
- [ ] Add retention policies
- [ ] Enable request logging

---

## Next Steps

- **[SDK Reference](./sdk-reference.md)** - Instrument your pipeline
- **[Configuration](./configuration.md)** - Advanced setup
- **[Best Practices](./best-practices.md)** - Tips and patterns
