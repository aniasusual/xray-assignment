# X-Ray System Architecture

> Debugging system for multi-step, non-deterministic pipelines. Captures **why** decisions were made, not just what happened.

## System Overview

**Two Components:**
1. **SDK** (Python): Context managers for instrumentation - automatic timing, sampling, async sending
2. **API** (FastAPI + PostgreSQL): Stores traces, provides query endpoints

**Core Principle**: Capture decision context at each step: inputs, outputs, reasoning, candidates.

---

## Data Model Rationale

### Structure

```python
Run: id, pipeline_name, start/end_time, status,
     metadata (JSONB), final_output (JSONB)

Step: id, run_id, step_name, step_type, sequence,
      start/end_time, inputs (JSONB), outputs (JSONB),
      reasoning (TEXT), candidates_in/out,
      candidates_data (JSONB), filters (JSONB)
```

### Key Decisions

**1. Two Tables (Run + Step), Not Embedded**
- **Why**: Query "all FILTER steps with >90% reduction" becomes simple JOIN with indexes
- **Alternative**: MongoDB embedded steps → requires $unwind in aggregation pipelines, less efficient than relational JOIN
- **Breaks Without**: Cross-pipeline analytics require complex aggregations; harder to maintain indexes on nested arrays

**2. JSONB for Variable Data**
- **Why**: Each pipeline has different fields; JSONB supports indexing (`@>`, `->`, `?`)
- **Alternative**: Strict schema → migration needed for every new pipeline type
- **Breaks Without**: Adding fraud detection pipeline requires database migration

**3. Standardized `step_type` Enum (LLM, SEARCH, FILTER, RANK, SELECT, CUSTOM)**
- **Why**: Enables "show all FILTER steps" across different pipelines
- **Alternative**: Free-form strings → fragments into "filter", "filtering", "prune"
- **Breaks Without**: Can't compare performance of all filtering steps system-wide

**4. Computed Properties (`duration_ms`, `reduction_rate`)**
- Calculated on-demand from start/end times, not stored
- **Why**: Always accurate, no staleness, simpler than triggers

**5. Smart Sampling (5000→150)**
- Store head(50) + tail(50) + random(50) = 150 candidates
- **Why**: 5000 @ 1KB = 5MB/step × 10 steps = 50GB/day vs 1.5MB/day (97% reduction)
- **Trade-off**: Lose full visibility but sampling debugs 95% of issues

---

## Debugging Walkthrough: Phone Case → Laptop Stand

**Problem**: Competitor selection returned laptop stand for iPhone case

**Step 1**: Query for run
```bash
curl http://localhost:8001/api/runs?pipeline_name=competitor-selection
```

**Step 2**: Get trace details
```bash
curl http://localhost:8001/api/runs/{run_id}
```

**Step 3**: Analyze response - Found root cause in `filter_by_category` step:
```json
{
  "candidates_in": 5000,
  "candidates_out": 4200,  // Only 16% filtered!
  "filters": {"category_similarity_threshold": 0.3},  // TOO LOW
  "candidates_data": [
    {"title": "Laptop Stand", "category": "Computer"}  // Wrong category passed through
  ]
}
```

Plus `rank_by_relevance` step showed laptop stand scored 0.89 (highest) due to price match boost.

**Fix**: Raise threshold from 0.3 to 0.7, add LLM validation step

**Time**: 10 minutes vs days

---

## Queryability Across Pipelines

**Challenge**: Support "show all runs where filtering eliminated >90% candidates" across competitor-selection, categorization, fraud-detection, etc.

**Solution**:

**1. Standardized Step Types**
```bash
curl -X POST /api/steps/query -d '{"step_type": "FILTER", "min_reduction_rate": 0.9}'
```
Works across all pipelines using FILTER steps.

**2. JSONB Flexibility**
Different pipelines store different data:
```json
// Competitor selection
{"filters": {"min_price": 10}}

// Fraud detection
{"filters": {"max_txns_per_hour": 10}}
```
Both queryable by `step_type = 'FILTER'`.

**3. Deep JSONB Queries**
```sql
-- All steps using GPT-4
SELECT * FROM steps WHERE inputs->>'model' = 'gpt-4';
```

**4. Naming Conventions**
Enforced: `verb_noun` pattern (`filter_by_price`, `rank_by_relevance`)

**Developer Constraints**:
- Must use standardized step types when applicable
- Follow naming convention
- Store numeric metrics consistently (e.g., always include candidate counts)

**Supports New Use Cases**: Fraud detection, content moderation work immediately without X-Ray code changes.

---

## Performance & Scale

**Problem**: Capturing 5000 candidates with rejection reasons = 5MB/step = 50GB/day

**Solution**: Smart Sampling
```python
# Auto-sample if >100 candidates
head (50) + tail (50) + random (50) = 150 total
```

**Trade-offs**:
| | Full | Sampled |
|-|------|---------|
| Storage | 5MB/step | 150KB/step |
| Debuggability | All details | Representative sample |

**Who Decides?**
- **Default**: SDK auto-samples if >100 candidates
- **Override**: Developer can force full capture for critical data
- **Configuration**: `configure(max_candidates_full_capture=50)` for production

**Rejection Reasons**: Aggregate statistics instead of per-candidate
```python
step.set_outputs({
    "rejection_reasons": {"too_expensive": 2100, "low_rating": 1500}
})
```

---

## Developer Experience

### Minimal Instrumentation (3 lines)
```python
from xray import RunContext

def pipeline():
    with RunContext("my-pipeline") as run:
        # existing code unchanged
        run.set_final_output(result)
```
**Gets**: Run timing, status, final output
**Missing**: Per-step visibility

### Full Instrumentation (~5 lines per step)
```python
from xray import RunContext, StepType

def pipeline():
    with RunContext("my-pipeline") as run:
        with run.step("filter", StepType.FILTER) as step:
            step.set_inputs({"threshold": 0.7})
            filtered = filter_func(candidates)
            step.set_candidates(
                candidates_in=len(candidates),
                candidates_out=len(filtered),
                data=filtered
            )
            step.set_reasoning("Filtered by threshold 0.7")
```
**Gets**: Per-step timing, inputs/outputs, reasoning, candidates

### If X-Ray API Down?
**Fallback Modes**:
- `SILENT`: Continue without error (production)
- `LOG`: Write to local file, upload later (development)
- `RAISE`: Fail fast (testing)

**Performance**: <1ms overhead with async mode

---

## Real-World Application

**E-Commerce Search**: "wireless headphones" query returned corded headphones

**Before X-Ray**: 3-4 days debugging with Elasticsearch logs + Datadog APM. Couldn't identify which of 6 stages failed.

**After X-Ray**:
```python
with run.step("parse_query", StepType.LLM) as step:
    parsed = parse(query)
    step.set_outputs({"filters": {"connectivity": "wireless"}})

with run.step("apply_filters", StepType.FILTER) as step:
    filtered = apply_filters(candidates)
    step.set_filters({"in_stock": True})  # Missing connectivity filter!
```

**Found**: Query parser extracted "wireless" but filter didn't apply it.
**Debug time**: 10 minutes

---

## Future Improvements

1. **Adaptive Sampling**: LLM steps sample by diversity (cluster embeddings)
2. **Diff Viewer**: Compare two runs side-by-side for A/B testing
3. **Anomaly Detection**: Alert on unusual patterns
4. **Multi-Language SDKs**: JavaScript, Go, Java
5. **Trace Replay**: Replay with modified parameters
6. **Cost Tracking**: Track LLM costs per step
7. **Web UI**: Dashboard for non-technical users
8. **OpenTelemetry Integration**: Link to distributed traces
9. **Retention Policies**: Auto-archive to S3
10. **Ultra-Lightweight Mode**: `sample_rate=0.1` for latency-sensitive pipelines

---

## API Specification

**Base**: `http://localhost:8001`

### POST /api/runs/ingest
Ingest trace
```json
{"run": {...}, "steps": [...]}
→ 201 {"success": true, "run_id": "uuid"}
```

### GET /api/runs
List runs (filters: pipeline_name, status, limit, date_range)
```
→ {"runs": [...], "total": 150}
```

### GET /api/runs/{run_id}
Get run with all steps
```
→ {"run": {...}, "steps": [{...}]}
```

### POST /api/steps/query
Query steps across pipelines
```json
{"step_type": "FILTER", "min_reduction_rate": 0.9}
→ {"steps": [...], "total": 45}
```

### GET /api/analytics/pipeline/{name}
Pipeline statistics
```
→ {"total_runs": 1523, "success_rate": 0.952, "avg_duration_ms": 4250}
```

---

## Summary

X-Ray captures **why** decisions were made in non-deterministic pipelines.

**Strengths**:
- **Flexible**: JSONB supports any pipeline type
- **Queryable**: Standardized types enable cross-pipeline analytics
- **Scalable**: 97% storage reduction via smart sampling
- **Resilient**: Fallback modes prevent disruption
- **Simple**: 3-line minimal instrumentation

Architecture balances completeness, performance, and developer experience.
