# X-Ray SDK and API - Complete Implementation Plan

## 📋 Project Overview

Building an **X-Ray system** for debugging multi-step, non-deterministic algorithmic pipelines. Unlike traditional distributed tracing (which answers "what happened?"), X-Ray answers **"why did the system make this decision?"**

### Key Differentiator

| Aspect | Traditional Tracing | X-Ray |
|--------|---------------------|-------|
| Focus | Performance & flow | Decision reasoning |
| Data | Spans, timing, service calls | Candidates, filters, selection logic |
| Question answered | "What happened?" | "Why this output?" |
| Granularity | Function/service level | Business logic level |

### Example Problem

**Scenario**: Competitor selection system for e-commerce
- Input: Seller's product (e.g., "Phone Case with Stand")
- Expected: Similar phone cases
- Actual: Laptop stand selected ❌

**Why X-Ray?** Traditional logs show what happened, but X-Ray reveals:
- LLM generated keyword "stand" from ambiguous title
- Search returned 5,000 candidates including laptop stands
- Filters eliminated 4,800 for category mismatch
- Root cause: Keyword generation step misinterpreted title

---

## 🎯 Deliverables

1. **X-Ray SDK** - Python library for instrumenting pipelines
2. **X-Ray API** - FastAPI backend with PostgreSQL
3. **Examples** - Working demos (competitor selection, listing optimization)
4. **ARCHITECTURE.md** - Technical documentation with diagrams
5. **Video Walkthrough** - 10-minute demo with face on camera

---

## 🏗️ Technology Stack

### Core Technologies
- **Language**: Python 3.9+
- **API Framework**: FastAPI
- **Database**: PostgreSQL 14+ with JSONB
- **ORM**: SQLAlchemy 2.0
- **Migrations**: Alembic
- **Package Manager**: Poetry
- **HTTP Client**: httpx (async support)

### Why These Choices?

**Python**: Matches the ML/data pipeline domain, rich ecosystem, easy to use

**FastAPI**:
- Modern async framework
- Auto-generated OpenAPI docs
- Type hints for validation
- High performance

**PostgreSQL + JSONB**:
- Structured data with flexible JSON columns
- Powerful JSONB queries (`@>`, `?`, `->`)
- ACID guarantees
- Indexes on JSON fields

**Poetry**:
- Modern dependency management
- Reproducible builds
- Easy packaging

---

## 📁 Project Structure

```
xray-assignment/
├── xray-sdk/                          # SDK Library
│   ├── xray/
│   │   ├── __init__.py               # Public API exports
│   │   ├── models.py                 # Data models (Run, Step)
│   │   ├── context.py                # Context managers with contextvars
│   │   ├── tracer.py                 # Main Tracer singleton
│   │   ├── client.py                 # HTTP client for API
│   │   ├── config.py                 # Configuration management
│   │   └── sampling.py               # Sampling strategies
│   ├── tests/
│   │   ├── test_context.py
│   │   ├── test_models.py
│   │   └── test_client.py
│   ├── pyproject.toml                # Poetry dependencies
│   └── README.md
│
├── xray-api/                          # API Service
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI application
│   │   ├── config.py                 # Settings with pydantic-settings
│   │   ├── database.py               # SQLAlchemy setup
│   │   ├── models.py                 # Database models
│   │   ├── schemas.py                # Pydantic request/response schemas
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── ingest.py            # POST /api/runs/ingest
│   │   │   └── query.py             # Query endpoints
│   │   └── services/
│   │       ├── __init__.py
│   │       └── query_service.py     # Business logic for queries
│   ├── alembic/                      # Database migrations
│   │   ├── versions/
│   │   └── env.py
│   ├── tests/
│   │   ├── test_ingest.py
│   │   └── test_query.py
│   ├── alembic.ini
│   ├── pyproject.toml
│   └── README.md
│
├── examples/                          # Demo Applications
│   ├── shared/
│   │   ├── __init__.py
│   │   └── mock_services.py         # Mock LLM/search functions
│   ├── competitor_selection.py      # Scenario A: Bad match demo
│   ├── listing_optimization.py      # Scenario B: Content generation
│   ├── query_examples.py            # How to query X-Ray data
│   └── README.md
│
├── docs/                              # Additional documentation
│   ├── diagrams/
│   │   ├── architecture.png
│   │   ├── data_model.png
│   │   └── debugging_flow.png
│   └── api_examples.md
│
├── ARCHITECTURE.md                    # Main architecture document
├── README.md                          # Project overview
├── .gitignore
└── docker-compose.yml                 # PostgreSQL for local dev
```

---

## 🧠 Core Concepts & Design

### 1. Data Model

#### Run Entity
Represents a complete pipeline execution.

```python
class Run:
    id: UUID                    # Unique identifier
    pipeline_name: str          # e.g., "competitor_selection"
    pipeline_version: str       # Track pipeline changes over time
    start_time: datetime
    end_time: datetime | None
    status: Enum                # success, failure, partial
    metadata: dict              # User-defined context (JSONB)
    final_output: dict | None   # The ultimate result (JSONB)
    error: str | None           # Error message if failed
```

#### Step Entity
Represents an individual stage in the pipeline.

```python
class Step:
    id: UUID
    run_id: UUID                # Foreign key to Run
    step_name: str              # e.g., "keyword_generation"
    step_type: str              # e.g., "llm", "filter", "search"
    sequence: int               # Order in pipeline (0, 1, 2...)
    start_time: datetime
    end_time: datetime
    duration_ms: int            # Computed: end - start

    # Decision context (JSONB):
    inputs: dict | None         # What went into this step
    outputs: dict | None        # What came out
    reasoning: str | None       # WHY this decision was made

    # Candidate tracking:
    candidates_in: int | None   # Count before step
    candidates_out: int | None  # Count after step
    candidates_data: dict | None # Full or sampled candidates (JSONB)

    # Filters and metadata:
    filters_applied: dict | None # Rules used (JSONB)
    metadata: dict | None        # Extensible metadata (JSONB)
    error: str | None            # Error if step failed
```

#### Design Rationale

**Why two-level hierarchy (Run → Steps)?**
- Simple, intuitive model
- Easy to query across pipelines
- Sufficient for most use cases
- Alternative (Step → SubSteps) adds complexity without clear value

**Why JSONB for inputs/outputs/metadata?**
- Each pipeline has different data shapes
- No schema changes needed for new pipeline types
- PostgreSQL JSONB is indexable and queryable
- Trade-off: Less type safety, more flexibility

**Why separate `candidates_in/out` from `candidates_data`?**
- Always store counts (lightweight, ~8 bytes)
- Conditionally store full data (expensive, could be MBs)
- Enables sampling strategies
- Solves the "5,000 candidates" scale problem

**Alternatives considered:**
1. **Fully normalized schema**: Separate Candidate table
   - ❌ Complex queries, many joins
   - ❌ Hard to support variable pipeline types
2. **Pure document store (MongoDB)**: No structured fields
   - ❌ Weak query capabilities
   - ❌ No ACID guarantees

### 2. SDK Design Pattern

**Approach**: Context Managers + Decorators (hybrid)

#### Context Manager Pattern (Primary)

```python
import xray

# Configure once at startup
xray.configure(
    api_url="http://localhost:8000",
    fallback_mode="silent",
    timeout=5.0
)

# Instrument pipeline
with xray.run("competitor_selection", metadata={"user_id": "123"}) as run:

    # Step 1: Keyword generation
    with run.step("keyword_generation", step_type="llm") as step:
        keywords = generate_keywords(product)
        step.set_inputs({"product": product.dict()})
        step.set_outputs(keywords)
        step.set_reasoning(f"Used {model_name} with temperature {temp}")

    # Step 2: Search
    with run.step("candidate_search", step_type="search") as step:
        candidates = search_catalog(keywords)
        step.set_inputs({"keywords": keywords})
        step.set_candidates(
            candidates,
            capture_mode="smart",  # Automatic sampling
            sample_size=100
        )

    # Step 3: Filter
    with run.step("price_filter", step_type="filter") as step:
        filtered = [c for c in candidates if 10 <= c.price <= 50]
        step.set_candidates_in(len(candidates))
        step.set_candidates_out(len(filtered))
        step.set_reasoning(f"Filtered by price range $10-$50")

    # Set final output
    run.set_output({"selected": best_match.dict()})
```

**Why context managers?**
- Automatic timing capture (`__enter__` records start, `__exit__` records end)
- Exception handling built-in
- Clear scope boundaries
- Pythonic pattern

#### Decorator Pattern (Optional, future)

```python
@xray.trace(step_name="filter_by_price", step_type="filter")
def filter_by_price(candidates, min_price, max_price):
    results = [c for c in candidates if min_price <= c.price <= max_price]
    xray.current_step().set_reasoning(f"Price range: ${min_price}-${max_price}")
    return results
```

**Why decorators?**
- Less intrusive
- Works with existing functions
- Automatic instrumentation

### 3. Thread-Safe Context Management

**Problem**: Need to track current run/step across nested context managers, potentially across threads/async tasks.

**Solution**: Python's `contextvars` module

```python
import contextvars

# Context variables (thread-safe, async-compatible)
_current_run: contextvars.ContextVar[Optional['Run']] = contextvars.ContextVar('current_run', default=None)
_current_step: contextvars.ContextVar[Optional['Step']] = contextvars.ContextVar('current_step', default=None)

class RunContext:
    def __enter__(self):
        self.token = _current_run.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _current_run.reset(self.token)
        # Send data to API
```

**Why contextvars over threading.local?**
- Works with asyncio
- Properly isolates contexts
- No leakage across requests

### 4. Sampling Strategy

**Problem**: Capturing 5,000+ candidates with full details is expensive (network, storage, query performance).

**Solution**: Tiered sampling with developer control

#### Smart Sampling (Default)

```python
def smart_sample(candidates, metadata=None):
    count = len(candidates)

    if count <= 100:
        # Capture everything
        return {
            "count": count,
            "sampled": False,
            "sample": [c.dict() for c in candidates]
        }

    elif count <= 1000:
        # Sample 100 + summary stats
        sample = random.sample(candidates, 100)
        return {
            "count": count,
            "sampled": True,
            "sample_size": 100,
            "sample": [c.dict() for c in sample],
            "summary": compute_summary(candidates)
        }

    else:
        # Sample 50 + detailed summary
        sample = random.sample(candidates, 50)
        return {
            "count": count,
            "sampled": True,
            "sample_size": 50,
            "sample": [c.dict() for c in sample],
            "summary": compute_detailed_summary(candidates, metadata)
        }

def compute_summary(candidates):
    """Aggregate statistics"""
    return {
        "price_range": [min(c.price), max(c.price)],
        "avg_rating": sum(c.rating) / len(candidates),
        "categories": Counter(c.category for c in candidates).most_common(10)
    }
```

#### Developer Control

```python
# Explicit modes
step.set_candidates(
    candidates,
    capture_mode="all"  # Force capture everything (warning if > 1000)
)

step.set_candidates(
    candidates,
    capture_mode="summary"  # Only counts + aggregates, no samples
)

step.set_candidates(
    candidates,
    capture_mode="sampled",
    sample_size=200,
    sample_strategy="representative"  # vs "random", "top_bottom"
)
```

#### Representative Sampling (Advanced)

For filtered candidates, capture:
- Top N by relevance score
- Bottom N to see edge cases
- Random N from middle

```python
def representative_sample(candidates, size=50):
    if len(candidates) <= size:
        return candidates

    # Assume candidates are sorted by score
    top = candidates[:size//3]
    bottom = candidates[-(size//3):]
    middle = random.sample(candidates[size//3:-(size//3)], size//3)

    return top + middle + bottom
```

**Trade-offs**:
- ✅ 10x-100x less data transferred/stored
- ✅ Fast queries
- ✅ Still see patterns via aggregates
- ❌ Can't see every rejected candidate
- ❌ Developer must choose appropriate mode

### 5. Queryability

**Challenge**: Support queries like "show all runs where filtering eliminated >90% candidates" across different pipeline types.

**Solution**: Conventions + PostgreSQL JSONB operators

#### Standard Step Types

SDK defines standard types (but allows custom):

```python
STANDARD_STEP_TYPES = [
    "llm",        # Language model calls
    "search",     # Search/retrieval operations
    "filter",     # Filtering/elimination
    "rank",       # Ranking/scoring
    "select",     # Final selection
    "transform",  # Data transformation
    "custom"      # User-defined
]
```

Developers use these when applicable:

```python
with run.step("price_filter", step_type="filter") as step:
    # SDK can now query across all filter steps
    pass
```

#### PostgreSQL JSONB Queries

Find runs with aggressive filtering:

```sql
SELECT DISTINCT r.*
FROM runs r
JOIN steps s ON s.run_id = r.id
WHERE s.step_type = 'filter'
  AND s.candidates_in > 0
  AND (s.candidates_out::float / s.candidates_in) < 0.1
ORDER BY r.start_time DESC
LIMIT 100;
```

Find all LLM steps using GPT-4:

```sql
SELECT s.*
FROM steps s
WHERE s.step_type = 'llm'
  AND s.metadata @> '{"model": "gpt-4"}'
ORDER BY s.start_time DESC;
```

#### Query API Examples

```python
# Python client
runs = xray_api.query_runs(
    filters={
        "pipeline_name": "competitor_selection",
        "date_range": ["2026-01-01", "2026-01-05"],
        "has_step": {
            "step_type": "filter",
            "reduction_rate_gt": 0.9  # Eliminated >90%
        }
    },
    limit=100
)

# Aggregation query
stats = xray_api.aggregate_steps(
    step_type="llm",
    group_by="metadata.model",
    metrics=["avg_duration", "count", "error_rate"]
)
```

**Conventions imposed on developers**:
1. Use standard step types when applicable
2. Store important metrics at top level (candidates_in/out)
3. Use consistent metadata keys (e.g., "model", "temperature")
4. Document custom conventions in team

**Extensibility**:
- JSONB supports arbitrary queries
- Developers can add custom indexes
- Trade-off: Some query knowledge required

### 6. API Design

#### Ingestion Endpoint

```
POST /api/v1/runs/ingest
Content-Type: application/json

Request Body:
{
  "run": {
    "id": "uuid",  // Optional: generated if not provided
    "pipeline_name": "competitor_selection",
    "pipeline_version": "1.0.0",
    "start_time": "2026-01-05T10:30:00Z",
    "end_time": "2026-01-05T10:30:05Z",
    "status": "success",
    "metadata": {
      "user_id": "123",
      "product_id": "abc",
      "environment": "production"
    },
    "final_output": {
      "selected_competitor": {...}
    }
  },
  "steps": [
    {
      "step_name": "keyword_generation",
      "step_type": "llm",
      "sequence": 0,
      "start_time": "2026-01-05T10:30:00Z",
      "end_time": "2026-01-05T10:30:01Z",
      "inputs": {"product": {...}},
      "outputs": ["phone", "case", "protective"],
      "reasoning": "Used GPT-4 with temperature 0.7",
      "metadata": {
        "model": "gpt-4",
        "temperature": 0.7,
        "tokens": 150
      }
    },
    {
      "step_name": "candidate_search",
      "step_type": "search",
      "sequence": 1,
      "start_time": "2026-01-05T10:30:01Z",
      "end_time": "2026-01-05T10:30:03Z",
      "inputs": {"keywords": ["phone", "case"]},
      "candidates_in": 0,
      "candidates_out": 5000,
      "candidates_data": {
        "count": 5000,
        "sampled": true,
        "sample_size": 50,
        "sample": [...]
      }
    },
    {
      "step_name": "price_filter",
      "step_type": "filter",
      "sequence": 2,
      "start_time": "2026-01-05T10:30:03Z",
      "end_time": "2026-01-05T10:30:04Z",
      "candidates_in": 5000,
      "candidates_out": 200,
      "filters_applied": {
        "price_min": 10,
        "price_max": 50
      },
      "reasoning": "Applied price range filter",
      "metadata": {
        "rejection_reasons": {
          "price_too_low": 500,
          "price_too_high": 4300
        }
      }
    }
  ]
}

Response (201 Created):
{
  "run_id": "uuid",
  "status": "success",
  "steps_ingested": 3
}
```

#### Query Endpoints

**Get specific run**:
```
GET /api/v1/runs/{run_id}

Response (200 OK):
{
  "run": {...},
  "steps": [...]
}
```

**Query runs**:
```
POST /api/v1/runs/query
Content-Type: application/json

Request Body:
{
  "pipeline_name": "competitor_selection",  // Optional
  "date_range": ["2026-01-01", "2026-01-05"],  // Optional
  "status": "success",  // Optional
  "metadata_filter": {  // Optional JSONB query
    "user_id": "123"
  },
  "has_step": {  // Optional: filter by step properties
    "step_type": "filter",
    "reduction_rate_gt": 0.9
  },
  "limit": 100,
  "offset": 0
}

Response (200 OK):
{
  "runs": [...],
  "total": 1543,
  "limit": 100,
  "offset": 0
}
```

**Get run steps**:
```
GET /api/v1/runs/{run_id}/steps

Response (200 OK):
{
  "run_id": "uuid",
  "steps": [...]
}
```

**Aggregate statistics**:
```
POST /api/v1/steps/aggregate
Content-Type: application/json

Request Body:
{
  "step_type": "llm",
  "group_by": "metadata.model",
  "metrics": ["avg_duration", "count", "p95_duration"]
}

Response (200 OK):
{
  "aggregations": [
    {
      "group": "gpt-4",
      "avg_duration_ms": 850,
      "count": 1250,
      "p95_duration_ms": 1500
    },
    {
      "group": "gpt-3.5-turbo",
      "avg_duration_ms": 420,
      "count": 5820,
      "p95_duration_ms": 750
    }
  ]
}
```

### 7. Developer Experience

#### Progressive Instrumentation

**Level 1: Minimal (5 minutes)**
```python
with xray.run("my_pipeline"):
    result = my_existing_pipeline()
```
- Captures: Run timing, status, errors
- Missing: Step-level visibility

**Level 2: Basic (30 minutes)**
```python
with xray.run("competitor_selection") as run:
    with run.step("search"):
        candidates = search()
    with run.step("filter"):
        filtered = filter_candidates(candidates)
    with run.step("select"):
        winner = select_best(filtered)
```
- Captures: Step names, timing, sequence
- Missing: Inputs, outputs, reasoning

**Level 3: Full (1-2 hours)**
```python
with xray.run("competitor_selection", metadata={"user": user_id}) as run:
    with run.step("keyword_gen", step_type="llm") as step:
        keywords = llm.generate(product)
        step.set_inputs({"product": product.dict()})
        step.set_outputs(keywords)
        step.set_reasoning(f"Model: {llm.model}")
        step.add_metadata({"tokens": llm.last_tokens})

    with run.step("search", step_type="search") as step:
        candidates = search(keywords)
        step.set_candidates(candidates, capture_mode="smart")

    with run.step("filter", step_type="filter") as step:
        filtered = apply_filters(candidates, filters)
        step.set_candidates_in(len(candidates))
        step.set_candidates_out(len(filtered))
        step.set_reasoning("Applied price and rating filters")
```
- Captures: Everything needed for debugging

#### Graceful Degradation

**If API is down**:

```python
xray.configure(
    api_url="http://localhost:8000",
    fallback_mode="silent",  # Options: "silent", "log", "raise"
    timeout=5.0
)

# With fallback_mode="silent":
# - API calls fail silently
# - Pipeline continues normally
# - No exceptions raised

# With fallback_mode="log":
# - Failed traces written to local file
# - Can bulk-upload later
# - File: ~/.xray/failed_traces/YYYY-MM-DD.jsonl

# With fallback_mode="raise":
# - Exceptions propagated
# - Use for testing
```

**Async mode** (non-blocking):

```python
xray.configure(
    api_url="http://localhost:8000",
    async_mode=True  # SDK sends data asynchronously
)

# SDK queues traces in-memory
# Background thread sends to API
# Pipeline doesn't wait for API response
```

---

## 🚀 Implementation Plan

### Phase 1: SDK Core (4-5 hours)

**Goal**: Build working SDK that can trace runs and steps.

#### Tasks

1. **Project setup** (30 min)
   ```bash
   mkdir xray-sdk && cd xray-sdk
   poetry init
   poetry add httpx pydantic python-dateutil
   poetry add --group dev pytest pytest-asyncio pytest-mock
   ```

2. **Data models** (`models.py`) (1 hour)
   - `RunModel`: id, pipeline_name, timestamps, metadata, etc.
   - `StepModel`: id, run_id, step_name, step_type, timing, data
   - Pydantic models with validation
   - JSON serialization methods

3. **Context management** (`context.py`) (1.5 hours)
   - `RunContext`: Context manager for runs
   - `StepContext`: Context manager for steps
   - Use `contextvars` for thread safety
   - Automatic timing capture
   - Exception handling

4. **HTTP client** (`client.py`) (1 hour)
   - Async client using `httpx`
   - `send_run()` method
   - Retry logic with exponential backoff
   - Timeout handling
   - Fallback modes

5. **Configuration** (`config.py`) (30 min)
   - `XRayConfig` class
   - Environment variables support
   - `configure()` function

6. **Sampling** (`sampling.py`) (1 hour)
   - `smart_sample()` function
   - `compute_summary()` for aggregates
   - Configurable strategies

7. **Public API** (`__init__.py`) (30 min)
   - `run()` function
   - `configure()` function
   - Export main classes

8. **Tests** (30 min)
   - Test context isolation
   - Test timing capture
   - Mock HTTP client

#### Success Criteria
- [ ] Can create runs and steps
- [ ] Timing automatically captured
- [ ] Data sent to API endpoint
- [ ] Graceful fallback when API down
- [ ] Tests passing

### Phase 2: API Backend (4-5 hours)

**Goal**: Build FastAPI service that ingests and queries X-Ray data.

#### Tasks

1. **Project setup** (30 min)
   ```bash
   mkdir xray-api && cd xray-api
   poetry init
   poetry add fastapi uvicorn[standard] sqlalchemy psycopg2-binary alembic pydantic-settings
   poetry add --group dev pytest pytest-asyncio httpx
   ```

2. **Database models** (`models.py`) (1 hour)
   - SQLAlchemy `Run` model
   - SQLAlchemy `Step` model
   - JSONB columns for flexible data
   - Indexes on: run_id, pipeline_name, step_type, timestamps
   - Relationships

3. **Pydantic schemas** (`schemas.py`) (45 min)
   - Request schemas: `IngestRunRequest`, `QueryRunsRequest`
   - Response schemas: `RunResponse`, `StepsResponse`
   - Validation rules

4. **Database setup** (`database.py`) (30 min)
   - SQLAlchemy engine and session
   - Connection pooling
   - Dependency injection for FastAPI

5. **Configuration** (`config.py`) (15 min)
   - Settings class with `pydantic-settings`
   - DATABASE_URL from env

6. **Alembic migrations** (30 min)
   ```bash
   alembic init alembic
   alembic revision --autogenerate -m "Initial schema"
   alembic upgrade head
   ```

7. **Ingestion endpoint** (`routers/ingest.py`) (1 hour)
   - `POST /api/v1/runs/ingest`
   - Validate request with Pydantic
   - Insert run and steps into DB
   - Transaction handling
   - Error responses

8. **Query endpoints** (`routers/query.py`) (1.5 hours)
   - `GET /api/v1/runs/{run_id}` - Get specific run
   - `POST /api/v1/runs/query` - Query with filters
   - `GET /api/v1/runs/{run_id}/steps` - Get run steps
   - Build dynamic SQL filters
   - Handle JSONB queries

9. **Query service** (`services/query_service.py`) (1 hour)
   - Extract query logic from routes
   - `build_query_filters()` function
   - JSONB filter builders
   - Pagination logic

10. **FastAPI app** (`main.py`) (30 min)
    - Create app instance
    - Include routers
    - CORS middleware
    - Exception handlers
    - Startup/shutdown events

11. **Tests** (1 hour)
    - Use FastAPI TestClient
    - Test ingest endpoint
    - Test query endpoints
    - Test error cases

#### Success Criteria
- [ ] Can ingest runs via POST
- [ ] Can query runs by ID
- [ ] Can filter runs by criteria
- [ ] Database schema correct
- [ ] Tests passing
- [ ] API docs at /docs

### Phase 3: Examples & Demo (2-3 hours)

**Goal**: Create working examples that demonstrate X-Ray in action.

#### Tasks

1. **Mock services** (`examples/shared/mock_services.py`) (45 min)
   - `MockLLM`: Simulates GPT calls with deterministic bugs
   - `MockSearchAPI`: Returns fake product candidates
   - `MockProduct`: Product data class
   - Helpers for generating test data

2. **Competitor selection example** (`examples/competitor_selection.py`) (1.5 hours)
   - Implement full pipeline:
     1. Keyword generation (LLM - with bug!)
     2. Candidate search
     3. Price filter
     4. Rating filter
     5. Category relevance (LLM)
     6. Final selection
   - Show GOOD run (phone case → phone case)
   - Show BAD run (phone case → laptop stand)
   - Include comments explaining each step

3. **Query/debug script** (`examples/query_examples.py`) (1 hour)
   - Query for bad runs
   - Examine step-by-step
   - Show how to identify root cause
   - Print human-readable output

4. **Documentation** (`examples/README.md`) (30 min)
   - How to run examples
   - What each example demonstrates
   - Expected output

#### Success Criteria
- [ ] Examples run end-to-end
- [ ] Data appears in database
- [ ] Can query and find bug
- [ ] Clear demonstration of value

### Phase 4: Architecture Document (2-3 hours)

**Goal**: Write comprehensive ARCHITECTURE.md addressing all requirements.

#### Required Sections

1. **System Overview** (30 min)
   - High-level architecture diagram (SDK → API → DB)
   - Component responsibilities
   - Data flow

2. **Data Model** (45 min)
   - Entity-relationship diagram
   - Table schemas
   - **Rationale**: Why JSONB? Why two-level hierarchy?
   - **Alternatives considered**: Normalized schema, NoSQL, etc.
   - **Trade-offs**: Flexibility vs type safety

3. **API Specification** (30 min)
   - Endpoint documentation
   - Request/response examples
   - Error codes

4. **Debugging Walkthrough** (45 min)
   - **Scenario**: Phone case → laptop stand bug
   - Step 1: Query for bad runs
   - Step 2: Examine steps
   - Step 3: Identify root cause (keyword generation)
   - Step 4: Fix and verify

5. **Queryability** (30 min)
   - How to query across pipelines
   - JSONB query examples
   - **Conventions**: Standard step types, metadata keys
   - **Extensibility**: Custom indexes, flexible queries
   - Trade-offs

6. **Performance & Scale** (30 min)
   - **Problem**: 5,000 candidates expensive to capture
   - **Solution**: Smart sampling strategy
   - **Trade-offs**: Completeness vs performance
   - **Developer control**: Capture modes
   - Future: Compression, archival, retention policies

7. **Developer Experience** (30 min)
   - Progressive instrumentation (minimal → full)
   - Code examples for each level
   - Failure modes and fallbacks
   - **If API down**: Silent, log, or raise

8. **Real-World Application** (30 min)
   - Example from your experience
   - How X-Ray would have helped
   - Estimated time savings

9. **Future Work** (15 min)
   - Real-time streaming
   - Visualization UI
   - Alerting
   - Multi-tenancy
   - SDK for other languages
   - ML on traces

#### Diagrams Needed

Create in Mermaid or draw.io:
- System architecture
- Data model ER diagram
- Debugging flow
- Query examples

#### Success Criteria
- [ ] All required sections present
- [ ] Clear, concise writing
- [ ] Specific, not generic
- [ ] Diagrams included
- [ ] Trade-offs discussed
- [ ] Real examples used

### Phase 5: Video & Polish (1-2 hours)

**Goal**: Record 10-minute video walkthrough and polish deliverables.

#### Video Structure (10 min max)

1. **Problem introduction** (1 min)
   - Show bad match scenario
   - Explain debugging pain without X-Ray

2. **Architecture overview** (3 min)
   - Walk through system diagram
   - Explain key design decisions
   - "I considered X but chose Y because..."

3. **Live demo** (4 min)
   - Run competitor selection example
   - Show good run vs bad run
   - Query API to find bug
   - Examine steps to identify root cause

4. **Reflection** (1.5 min)
   - One challenge you faced
   - How you solved it
   - What you learned

5. **Wrap-up** (30 sec)
   - Summary of value prop
   - Future directions

#### Tips

- Write bullet points, don't script word-for-word
- Practice once to check timing
- Be conversational, not formal
- Point at code/diagrams as you explain
- Show your face on camera
- Use screen recording: Loom, OBS, or QuickTime

#### Polish Tasks

1. **README files** (30 min)
   - Main README: Project overview, setup, usage
   - SDK README: Installation, quick start, API reference
   - API README: Running locally, endpoints, configuration
   - Examples README: How to run, what they show

2. **Code cleanup** (30 min)
   - Remove debug prints
   - Add docstrings to public functions
   - Format with `black`
   - Type hints
   - Remove TODOs

3. **Testing** (30 min)
   - Run all tests
   - Fix any failures
   - Test examples end-to-end

4. **Git** (15 min)
   - Write clear commit messages
   - Clean git history (squash if messy)
   - Add .gitignore

#### Success Criteria
- [ ] Video under 10 minutes
- [ ] Face visible on camera
- [ ] Live demo works
- [ ] Clear, engaging explanation
- [ ] READMEs complete
- [ ] Code clean and tested
- [ ] Ready to submit

---

## 📚 Key Technical Concepts

### FastAPI

Modern Python web framework:
- Async/await support (fast!)
- Automatic data validation with Pydantic
- Auto-generated OpenAPI docs at `/docs`
- Type hints for editor autocomplete

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.post("/items/")
async def create_item(item: Item):
    # item is validated automatically
    return {"id": 1, "name": item.name}
```

### SQLAlchemy 2.0

ORM for database interaction:
- Maps Python classes to tables
- Type-safe queries
- Relationship management

```python
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID, primary_key=True)
    pipeline_name = Column(String, index=True)
    metadata = Column(JSONB)  # PostgreSQL JSONB type

    steps = relationship("Step", back_populates="run")
```

### PostgreSQL JSONB

Binary JSON storage with query support:

```sql
-- Find runs with specific metadata
SELECT * FROM runs
WHERE metadata @> '{"user_id": "123"}';

-- Query nested JSON
SELECT * FROM steps
WHERE metadata->>'model' = 'gpt-4';

-- Array contains
SELECT * FROM steps
WHERE outputs @> '["phone", "case"]';
```

**JSONB operators**:
- `@>`: Contains (left contains right)
- `?`: Key exists
- `->`: Get JSON object
- `->>`: Get JSON as text
- `#>`: Get nested path

### contextvars

Thread-safe context management (Python 3.7+):

```python
import contextvars

# Create context variable
current_user = contextvars.ContextVar('current_user')

def process_request(user):
    # Set context
    token = current_user.set(user)
    try:
        do_work()  # Can access current_user inside
    finally:
        current_user.reset(token)

def do_work():
    user = current_user.get()  # Gets current user
```

Works with:
- Threading
- Asyncio
- Concurrent.futures

### Pydantic

Data validation with type hints:

```python
from pydantic import BaseModel, Field, validator

class Product(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    price: float = Field(..., gt=0)
    tags: list[str] = []

    @validator('price')
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('must be positive')
        return v

# Automatic validation
product = Product(name="Phone", price=99.99)  # ✅
product = Product(name="", price=-10)  # ❌ ValidationError
```

### Alembic

Database migrations:

```bash
# Create migration
alembic revision --autogenerate -m "Add column"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## ⚠️ Common Pitfalls

1. **Over-engineering**
   - ❌ Building full distributed tracing system
   - ✅ Focus on MVP, core value prop

2. **Generic architecture doc**
   - ❌ "We use PostgreSQL because it's scalable"
   - ✅ "We use PostgreSQL JSONB because each pipeline has different data shapes, and JSONB indexes enable flexible queries while maintaining ACID guarantees"

3. **No actual demo**
   - ❌ Just talking about architecture
   - ✅ Show working code, run examples, query results

4. **Ignoring trade-offs**
   - ❌ "Our sampling strategy is perfect"
   - ✅ "Sampling reduces completeness but enables 100x better performance. For 99% of debugging, aggregates + samples are sufficient."

5. **Bad database schema**
   - ❌ Trying to normalize everything
   - ✅ Use JSONB for variable data, structured columns for queryable fields

6. **10+ minute video**
   - ❌ Rambling, no structure
   - ✅ Practice, time yourself, cut ruthlessly

7. **Not addressing requirements**
   - ❌ Missing sections in ARCHITECTURE.md
   - ✅ Use checklist, address every point

---

## ✅ Success Checklist

### SDK
- [ ] Context managers for runs and steps
- [ ] Automatic timing capture
- [ ] Thread-safe with contextvars
- [ ] HTTP client with retry/fallback
- [ ] Sampling strategies
- [ ] Configuration management
- [ ] Tests passing

### API
- [ ] FastAPI application
- [ ] PostgreSQL database with JSONB
- [ ] Ingest endpoint working
- [ ] Query endpoints working
- [ ] Proper error handling
- [ ] Database migrations
- [ ] Tests passing
- [ ] API docs at /docs

### Examples
- [ ] Competitor selection demo (good + bad runs)
- [ ] Query script showing debugging workflow
- [ ] Mock services for reproducibility
- [ ] Clear documentation

### Architecture Doc
- [ ] System architecture diagram
- [ ] Data model with rationale
- [ ] API specification
- [ ] Debugging walkthrough (phone case bug)
- [ ] Queryability explanation
- [ ] Performance & scale discussion
- [ ] Developer experience examples
- [ ] Real-world application story
- [ ] Future work section

### Video
- [ ] Under 10 minutes
- [ ] Face on camera
- [ ] Problem introduction
- [ ] Architecture walkthrough
- [ ] Live demo
- [ ] Reflection on challenges
- [ ] Uploaded (YouTube unlisted or Loom)

### Polish
- [ ] Clear README files
- [ ] Code formatted and clean
- [ ] Tests passing
- [ ] Git history clean
- [ ] .gitignore configured

### Submission
- [ ] Submitted via form: https://forms.gle/YyPDaZn6NFmcef6e9

---

## 🎯 Focus Areas

Based on evaluation criteria (in order of importance):

### 1. System Design (40%)
- Clean SDK architecture
- Extensible, general-purpose
- Good abstractions
- Developer-friendly API

### 2. First Principles Thinking (30%)
- Clear rationale for every choice
- Articulate trade-offs
- "Why" not just "what"
- Show you broke down the problem

### 3. Communication (20%)
- Architecture doc: Clear, concise, insightful
- Video: Engaging, structured, shows understanding
- No AI slop, genuine reasoning

### 4. Code Quality (10%)
- Clean, readable
- Sensible abstractions
- Good separation of concerns
- Works as demonstrated

---

## 💡 Pro Tips

1. **Start with the SDK** - Get developer experience right first
2. **Test as you go** - Don't wait until end for integration testing
3. **Keep it simple** - MVP beats perfect. Ship it.
4. **Document decisions** - Comment your code with "why", not "what"
5. **Time management** - Don't spend 4 hours on sampling algorithms
6. **Architecture doc first** - Write it early, refine as you code
7. **Video prep** - Bullet points, not scripts. Practice once.
8. **Show trade-offs** - Every design choice has pros/cons. Discuss them.

---

## 📖 Resources

- **FastAPI**: https://fastapi.tiangolo.com/
- **SQLAlchemy**: https://docs.sqlalchemy.org/
- **PostgreSQL JSONB**: https://www.postgresql.org/docs/current/datatype-json.html
- **Pydantic**: https://docs.pydantic.dev/
- **contextvars**: https://docs.python.org/3/library/contextvars.html
- **Alembic**: https://alembic.sqlalchemy.org/

---

## 🚀 Let's Build!

You have everything you need:
- Clear problem statement
- Solid technology choices
- Detailed implementation plan
- Examples and patterns

Now it's time to **ship it**. Focus on:
- Making the SDK delightful to use
- Making the architecture doc insightful (not generic)
- Making the video engaging (tell a story)

Good luck! You've got this. 🎉
