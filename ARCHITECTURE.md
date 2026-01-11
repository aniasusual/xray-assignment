# X-Ray System Architecture

> A debugging system for multi-step, non-deterministic pipelines that captures the "why" behind decisions.

## System Overview

![System Architecture](./diagrams/system-architecture.png)

X-Ray consists of two components:
1. **SDK** (Python library): Context managers that instrument code with automatic timing, sampling, and async sending
2. **API** (FastAPI + PostgreSQL): Stores traces and provides query endpoints

**Key Design Principle**: Capture decision context (inputs, outputs, reasoning, candidates) at each step, not just timing.

### Pipeline Execution Flow

![Pipeline Execution Flow](./diagrams/pipeline-execution-flow.png)

---

## Data Model Rationale

### Core Structure

![Data Model](./diagrams/data-model.png)

```python
Run {
    id, pipeline_name, pipeline_version,
    start_time, end_time, status,
    metadata: JSONB,           # Flexible context
    final_output: JSONB        # End result
}

Step {
    id, run_id, step_name, step_type, sequence,
    start_time, end_time,
    inputs: JSONB,             # Parameters used
    outputs: JSONB,            # What was produced
    reasoning: str,            # WHY this decision
    candidates_in, candidates_out,
    candidates_data: JSONB,    # Sampled candidates
    filters_applied: JSONB,
    metadata: JSONB
}
```

### Design Decisions

#### 1. Two-Table Design (Run + Step)

**Decision**: Separate tables, not embedded documents.

**Why**:
- **Query Performance**: "Show all FILTER steps with >90% reduction" becomes simple indexed SQL query
- **Independence**: Can query steps across runs without loading full run documents
- **Joins**: PostgreSQL optimizes this well

**Rejected Alternative**: MongoDB with embedded steps
- Would require full document scans for cross-pipeline queries
- No way to efficiently index step-level attributes across runs

**What Would Break**: Without separation, cross-pipeline queries like "find all LLM steps >5s" require scanning every run and extracting nested arrays. With indexes on `step_type` and `start_time`, this is O(log n).

#### 2. JSONB for Variable Data

**Decision**: Use PostgreSQL JSONB for `inputs`, `outputs`, `metadata`, `filters_applied`, `candidates_data`.

**Why**:
- Different pipelines have different fields (competitor selection has "keywords", categorization has "confidence_scores")
- JSONB supports indexing and operators (`@>`, `->`, `?`)
- Still Pydantic-validated before storage
- More efficient than text JSON

**Rejected Alternative**: Strict schema with columns for every field
- Impossible to predict all future use cases
- Would need migrations for every new pipeline type

**What Would Break**: With strict schema, adding image classification pipeline would need database migration + API changes. With JSONB, it works immediately.

#### 3. Standardized `step_type` Enum

**Decision**: Enforce enum (LLM, SEARCH, FILTER, RANK, SELECT, TRANSFORM, CUSTOM).

**Why**:
- Enables cross-pipeline queries: "show all LLM steps"
- Can compare performance of all FILTER steps system-wide
- Forces developers to think in standard patterns

**Rejected Alternative**: Free-form strings
- Would fragment into "filter", "filtering", "apply_filters", "prune"
- Cross-pipeline analytics become impossible

**What Would Break**: Without standardization, the query "compare avg reduction rates for FILTER vs RANK" fails due to inconsistent naming.

#### 4. Computed Properties (Not Stored)

**Decision**: `duration_ms` and `reduction_rate` computed on-demand, not stored as columns.

**Why**:
- Always accurate (derived from source of truth)
- No data duplication
- Can change calculation without migration

**What Would Break**: If stored and someone updates `start_time`, `duration_ms` becomes stale unless we add triggers (complexity).

#### 5. Sampling in `candidates_data`

**Decision**: Store head (50) + tail (50) + random (50) = ~150 sampled candidates, not all.

**Why**:
- 5000 candidates @ 1KB each = 5MB per step
- 10 steps = 50MB per run
- 1000 runs/day = 50GB/day
- Sampling = 97% storage reduction

**Trade-off**: Lose ability to see ALL rejected candidates, but sampling debugs 95% of issues.

---

## Debugging Walkthrough

### Scenario: Phone Case Matched Against Laptop Stand

**Problem**: Competitor selection returned "Adjustable Aluminum Laptop Stand" for "iPhone 15 Pro Silicone Case"

![Debugging Flow](./diagrams/debugging-flow.png)

#### Investigation

**1. Query for problematic run**:
```bash
curl http://localhost:8001/api/runs?pipeline_name=competitor-selection
# Find run with wrong output
```

**2. Get detailed trace**:
```bash
curl http://localhost:8001/api/runs/{run_id}
```

**3. Inspect steps** - Found two issues:

**Issue #1 - Step 2 (filter_by_category)**:
```json
{
  "candidates_in": 5000,
  "candidates_out": 4200,  // Only 16% filtered!
  "filters_applied": {
    "category_similarity_threshold": 0.3  // TOO LOW
  },
  "candidates_data": [
    {"title": "iPhone 15 Case", "category": "Cell Phone"},
    {"title": "Laptop Stand", "category": "Computer"}  // ⚠️ Got through!
  ]
}
```

**Issue #2 - Step 3 (rank_by_relevance)**:
```json
{
  "candidates_data": [
    {"title": "Laptop Stand", "score": 0.89},  // ⚠️ Ranked #1!
    {"title": "iPhone Case", "score": 0.87}
  ],
  "reasoning": "Ranked by embedding similarity with price match boost"
}
```

**Root Cause**:
1. Filter threshold too low (0.3) let laptop stand through
2. Ranking boosted by price match (both ~$20)
3. Missing LLM validation step

**Fix**:
```python
# Raise threshold
filters_applied = {"category_similarity_threshold": 0.7}

# Add validation step
with StepContext("llm_validate_category", StepType.LLM) as step:
    validated = llm_check_category_match(candidates)
    step.set_reasoning("GPT-4 validated category match")
```

**Verify**:
```bash
curl -X POST /api/steps/query \
  -d '{"step_name": "filter_by_category"}'
# Old: 5000→4200 (16% reduction)
# New: 5000→500 (90% reduction)
```

**Time to debug**: ~10 minutes vs hours/days without X-Ray

---

## Queryability

### Cross-Pipeline Support

The system enables queries across different pipeline types through:

**1. Standardized Step Types**

All pipelines use the same enum:
```python
StepType = LLM | SEARCH | FILTER | RANK | SELECT | TRANSFORM | CUSTOM
```

Example query: "Show all FILTER steps with >90% reduction"
```bash
curl -X POST /api/steps/query \
  -d '{"step_type": "FILTER", "min_reduction_rate": 0.9}'
```

Works across:
- Competitor selection (filter_by_category)
- Listing optimization (filter_low_performing)
- Categorization (filter_by_confidence)

**2. JSONB Flexibility**

Different pipelines store different data:
```json
// Competitor selection
{"filters_applied": {"min_price": 10, "max_price": 50}}

// Categorization
{"filters_applied": {"min_confidence": 0.8}}
```

Both queryable with `step_type = 'FILTER'`.

**3. Deep JSONB Queries**

```sql
-- Find all steps using GPT-4
SELECT * FROM steps WHERE inputs->>'model' = 'gpt-4';

-- High price filters
SELECT * FROM steps WHERE (filters_applied->>'min_price')::float > 100;
```

**4. Naming Conventions**

Enforced: `verb_noun` pattern
- ✅ `filter_by_price`, `rank_by_relevance`
- ❌ `step1`, `processing`

### Supporting Million Use Cases

![Cross-Pipeline Query](./diagrams/cross-pipeline-query.png)

Example - Fraud Detection (completely different domain):
```python
with RunContext("fraud-detection") as run:
    with StepContext("check_velocity", StepType.FILTER) as step:
        step.set_inputs({"max_txns_per_hour": 10})
        step.set_candidates(flagged, previous_count=all_txns)
```

Works immediately - no X-Ray code changes needed.

---

## Performance & Scale

### The 5000→30 Problem

**Challenge**: Capturing all 5000 candidates = 5MB per step = 50GB/day

### Solution: Smart Sampling

![Sampling Strategy](./diagrams/sampling-strategy.png)

```python
def smart_sample(candidates, max_full=100, sample_size=50):
    if len(candidates) <= max_full:
        return candidates  # Full capture

    # Sample ~150 total
    return (
        candidates[:50] +           # Head (what came in)
        candidates[-50:] +          # Tail (what survived)
        random.sample(middle, 50)   # Random (representative)
    )
```

**Results**: 5000→150 = 97% storage reduction

**Trade-offs**:

| Aspect | Full | Sampled |
|--------|------|---------|
| Storage | 5MB/step | 150KB/step |
| Bandwidth | 50MB/run | 1.5MB/run |
| Debuggability | All details | Representative |
| Query Speed | Slow | Fast |

### Who Decides?

**Default**: SDK auto-samples if >100 candidates
```python
step.set_candidates(filtered, previous_count=5000)  # Auto-sampled
```

**Override**: Developer forces full capture
```python
step.set_candidates(critical_data, auto_sample=False)  # All stored
```

**Configuration**: Global control
```python
configure(max_candidates_full_capture=50)   # Production
configure(max_candidates_full_capture=500)  # Development
```

### Rejection Reasons

Can't capture per-candidate reasons for all 4970 rejected items.

**Solution**: Aggregate statistics
```python
step.set_outputs({
    "rejection_reasons": {
        "too_expensive": 2100,
        "too_cheap": 1500,
        "out_of_stock": 800
    }
})
```

Provides high-level insight + sampled examples.

---

## Developer Experience

### Instrumenting Existing Pipeline

**Original code**:
```python
def select_competitor(product_title):
    keywords = generate_keywords(product_title)
    candidates = search_catalog(keywords)
    filtered = filter_by_category(candidates)
    ranked = rank_by_relevance(filtered)
    return select_top(ranked)
```

### (a) Minimal Instrumentation

![Instrumentation Levels](./diagrams/instrumentation-levels.png)

Add 3 lines:
```python
from xray import RunContext, configure

configure(api_url="http://localhost:8001")

def select_competitor(product_title):
    with RunContext("competitor-selection") as run:
        # ... existing code unchanged ...
        run.set_final_output({"selected": result})
        return result
```

**Get**: Start/end time, status, final output
**Missing**: Per-step visibility

### (b) Full Instrumentation

Add ~5 lines per step:
```python
from xray import RunContext, StepContext, StepType

def select_competitor(product_title):
    with RunContext("competitor-selection") as run:

        with StepContext("generate_keywords", StepType.LLM) as step:
            step.set_inputs({"product_title": product_title})
            keywords = generate_keywords(product_title)
            step.set_outputs({"keywords": keywords})
            step.set_reasoning("GPT-4 extracted keywords")

        with StepContext("search_catalog", StepType.SEARCH) as step:
            candidates = search_catalog(keywords)
            step.set_candidates(candidates)  # Auto-sampled

        # ... more steps ...
```

**Get**: Per-step timing, inputs/outputs, reasoning, candidates, reduction rates

### (c) If X-Ray API is Down?

![Fallback Modes](./diagrams/fallback-modes.png)

**Fallback modes**:

```python
# Production: Silent (continue without error)
configure(fallback_mode=FallbackMode.SILENT, timeout_seconds=2.0)
# Overhead if API down: ~0.25ms

# Development: Log to file
configure(fallback_mode=FallbackMode.LOG, log_file="/tmp/xray.jsonl")
# Upload later: xray upload /tmp/xray.jsonl

# Testing: Fail fast
configure(fallback_mode=FallbackMode.RAISE)
# Catch infrastructure issues in CI
```

**Async mode** (default): Trace sent in background thread, pipeline doesn't wait

**Disable entirely**:
```python
configure(enabled=False)  # Zero overhead
```

### Performance Impact

| Mode | Overhead/Step | Overhead/Run |
|------|---------------|--------------|
| Disabled | 0.01ms | 0.05ms |
| Async | 0.25ms | 1-2ms |
| Sync | 50ms | 500ms (10 steps) |

**Recommendation**: Always use async in production.

---

## Real-World Application

### E-Commerce Search Relevance

At a previous company, search system had 6 stages: query understanding → retrieval → pre-filter → ML ranking → post-processing → selection.

**Problem**: "Search for 'wireless headphones' returns corded headphones in top 10"

**Tools we had**: Elasticsearch logs, Datadog APM (timing only), scattered app logs

**What we couldn't see**: Which stage failed? Did ML rank corded highly? Were wireless filtered out? Was query misunderstood?

**Debug time**: 3-4 days

### With X-Ray

After instrumenting with X-Ray:

```python
with RunContext("product-search", metadata={"query": query}) as run:
    with StepContext("parse_query", StepType.LLM) as step:
        parsed = parse(query)
        step.set_outputs({"filters": {"connectivity": "wireless"}})

    with StepContext("apply_business_rules", StepType.FILTER) as step:
        filtered = apply_filters(candidates)
        step.set_filters_applied({"in_stock": True, "ships_to_us": True})
        # ⚠️ Missing connectivity filter!
```

**Found issue**: Query parser extracted `connectivity: wireless`, but pre-filter didn't apply it.

**Debug time**: 10 minutes

**Benefits**:
- Historical debugging: "Show all searches where 'wireless' returned corded"
- Performance: "Which stage is slowest?"
- A/B testing: "Compare ML model v1 vs v2"

---

## Future Improvements

### If Shipping for Production

1. **Adaptive Sampling**: LLM steps sample by diversity (cluster embeddings), FILTER steps sample rejections
2. **Diff Viewer**: `POST /api/runs/diff` to compare two runs side-by-side for A/B testing
3. **Anomaly Detection**: Background job alerts on unusual patterns (filter suddenly reducing 99%)
4. **Multi-Language SDKs**: JavaScript, Go, Java with same API
5. **Trace Replay**: Export trace, replay locally with modified parameters
6. **Cost Tracking**: Track LLM costs per step, query "total cost per pipeline per day"
7. **Web UI**: React dashboard for non-technical users
8. **OpenTelemetry Integration**: Link X-Ray steps to distributed traces
9. **Retention Policies**: Auto-archive old runs to S3
10. **Ultra-Lightweight Mode**: `sample_rate=0.1` for latency-sensitive pipelines

---

## API Specification

### Base: `http://localhost:8001`

#### Health Check
```http
GET /health
→ {"status": "healthy", "service": "xray-api"}
```

#### Ingest Trace
```http
POST /api/runs/ingest
Content-Type: application/json

{
  "run": {
    "id": "uuid", "pipeline_name": "X", "start_time": "...",
    "status": "SUCCESS", "metadata": {}, "final_output": {}
  },
  "steps": [{...}]
}

→ 201 {"success": true, "run_id": "uuid", "steps_count": 5}
```

#### List Runs
```http
GET /api/runs?pipeline_name=X&status=SUCCESS&limit=50&offset=0

→ {"runs": [...], "total": 150, "page": 1, "page_size": 50}
```

#### Get Run with Steps
```http
GET /api/runs/{run_id}

→ {"run": {...}, "steps": [{...}]}
```

#### Query Steps (Cross-Pipeline)
```http
POST /api/steps/query
Content-Type: application/json

{
  "step_type": "FILTER",
  "min_reduction_rate": 0.9,
  "min_duration_ms": 1000
}

→ {"steps": [...], "total": 45}
```

#### Analytics Summary
```http
GET /api/analytics/summary?pipeline_name=X&days=30

→ {
  "runs": {"total": 1523, "successful": 1450, "success_rate": 0.952},
  "performance": {"avg_duration_ms": 4250, "p95_duration_ms": 6800},
  "steps": {"slowest_step": "llm_validate"}
}
```

#### Analytics by Step Type
```http
GET /api/analytics/by-step-type?pipeline_name=X

→ {
  "step_types": [
    {"step_type": "LLM", "count": 3045, "avg_duration_ms": 1850},
    {"step_type": "FILTER", "avg_reduction_rate": 0.72}
  ]
}
```

**Error Format**: `{"detail": "message"}`
**Status Codes**: 200 (OK), 201 (Created), 400 (Bad Request), 404 (Not Found), 500 (Error)

---

## Diagrams

All diagrams are embedded throughout this document. See `diagrams/` folder for PNG files:
- `system-architecture.png` - Overall system flow (System Overview)
- `pipeline-execution-flow.png` - SDK execution sequence (System Overview)
- `data-model.png` - Database ER diagram (Data Model Rationale)
- `debugging-flow.png` - Investigation walkthrough (Debugging Walkthrough)
- `cross-pipeline-query.png` - Querying across pipelines (Queryability)
- `sampling-strategy.png` - Smart sampling visualization (Performance & Scale)
- `fallback-modes.png` - API down handling (Developer Experience)
- `instrumentation-levels.png` - Minimal vs full (Developer Experience)

Mermaid source code in `diagrams/mermaid-diagrams.md`

---

## Conclusion

X-Ray provides visibility into non-deterministic, multi-step pipelines by capturing decision context at each stage.

**Key Strengths**:
- **Flexible**: JSONB allows any pipeline type without schema changes
- **Queryable**: Standardized types enable cross-pipeline analytics
- **Scalable**: Smart sampling reduces storage by 97%
- **Resilient**: Fallback modes prevent pipeline disruption
- **Developer-Friendly**: 3-line minimal instrumentation

The architecture balances completeness, performance, and ease of use for real-world deployment.
