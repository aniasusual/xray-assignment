# X-Ray Documentation

Complete documentation for the X-Ray debugging system.

## 📚 Documentation Index

### Getting Started

- **[Getting Started](./getting-started.md)** - Installation and first pipeline
  - What is X-Ray?
  - Installation
  - Your first instrumented pipeline
  - Quick tips

- **[Integration Guide](./integration-guide.md)** - Using X-Ray in production ⭐
  - How X-Ray actually works
  - Real-world FastAPI integration example
  - Where output is visible (API, not terminal!)
  - Debugging workflows (curl, scripts, dashboards)
  - Common usage patterns

### Reference

- **[SDK Reference](./sdk-reference.md)** - Complete Python SDK API
  - Configuration
  - RunContext
  - StepContext
  - Data models
  - Environment variables

- **[API Reference](./api-reference.md)** - REST API endpoints
  - Ingest traces
  - Query runs and steps
  - Analytics
  - Interactive docs

### Guides

- **[Best Practices](./best-practices.md)** - Tips and patterns
  - Instrumentation guidelines
  - Configuration per environment
  - Performance optimization
  - Data quality
  - Security
  - Common patterns

## Quick Links

### For Developers

- **New to X-Ray?** Start with [Getting Started](./getting-started.md)
- **Need API details?** See [SDK Reference](./sdk-reference.md)
- **Want examples?** Check [../examples/](../examples/)

### For Operators

- **Deploying X-Ray?** See [API Reference](./api-reference.md#deployment)
- **Monitoring?** See [Best Practices](./best-practices.md#maintenance)
- **Debugging issues?** See [Best Practices](./best-practices.md#debugging)

## What is X-Ray?

X-Ray is a debugging system for multi-step, non-deterministic pipelines. It answers the question:

> **"Why did my pipeline make this decision?"**

Not just "what happened" (traditional logging) but **why** it happened.

### Use Cases

- **AI/LLM Pipelines** - Why did the model generate this output?
- **Search & Ranking** - Why did this result rank #1?
- **Recommendation Systems** - Why was this item recommended?
- **Competitor Selection** - Why was this competitor chosen?
- **Content Moderation** - Why was this flagged?
- **Fraud Detection** - Why was this transaction blocked?

### Key Features

1. **Context Managers** - Automatic timing, no manual code
2. **Smart Sampling** - 5000→150 candidates (97% reduction)
3. **Reasoning** - Each step explains WHY
4. **Cross-Pipeline Queries** - Find patterns across all pipelines
5. **Async Mode** - Non-blocking, <1ms overhead
6. **Resilient** - Continues if API is down

## Quick Example

```python
from xray import RunContext, StepContext, StepType, configure

configure(api_url="http://localhost:8001")

def find_competitor(product_title):
    with RunContext("competitor-selection") as run:

        # Step 1: Generate keywords
        with StepContext("generate_keywords", StepType.LLM) as step:
            keywords = llm_extract_keywords(product_title)
            step.set_outputs({"keywords": keywords})
            step.set_reasoning("Used GPT-4 to extract search keywords")

        # Step 2: Search catalog
        with StepContext("search", StepType.SEARCH) as step:
            results = search_catalog(keywords)
            step.set_candidates(results)  # Auto-sampled if >100
            step.set_reasoning("Searched product catalog")

        # Step 3: Filter by category
        with StepContext("filter", StepType.FILTER) as step:
            filtered = filter_by_category(results)
            step.set_candidates(filtered, previous_count=len(results))
            step.set_reasoning("Filtered by category similarity")

        best = filtered[0]
        run.set_final_output({"competitor": best})
        return best
```

**Query the data**:
```bash
curl http://localhost:8001/api/runs/{run_id}
```

**Get insights**:
- See timing for each step
- Track 1000→500→50 candidate flow
- Understand why decisions were made
- Debug issues in minutes (not hours)

## Architecture

```
┌─────────────────┐
│  Your Pipeline  │  ← Instrument with context managers
└────────┬────────┘
         │ Auto-capture: timing, candidates, reasoning
         ↓
┌─────────────────┐
│    X-Ray SDK    │  ← Smart sampling, async send
└────────┬────────┘
         │ POST /api/runs/ingest
         ↓
┌─────────────────┐
│   X-Ray API     │  ← Store & query
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   PostgreSQL    │  ← JSONB for flexibility
└─────────────────┘
```

## Documentation Structure

```
docs/
├── README.md                    # This file (index)
├── getting-started.md          # Installation & first pipeline
├── sdk-reference.md            # Complete SDK API
├── api-reference.md            # REST API endpoints
└── best-practices.md           # Tips and patterns
```

## Related Resources

- **[ARCHITECTURE.md](../ARCHITECTURE.md)** - Technical deep-dive
  - Data model rationale
  - Debugging walkthrough
  - Performance & scale
  - Design decisions

- **[Examples](../examples/)** - Real-world demos
  - Competitor selection pipeline
  - Debugging walkthrough
  - Complete end-to-end flow

- **[QUICKSTART.md](../QUICKSTART.md)** - Setup guide
  - Database setup
  - Running tests
  - API commands

## Support

### Getting Help

1. **Check the docs** - Most questions are answered here
2. **See examples** - Real-world patterns in `examples/`
3. **Read ARCHITECTURE.md** - Deep technical details
4. **Search issues** - GitHub issues tracker
5. **Ask in discussions** - Community Q&A

### Reporting Issues

Please include:
- X-Ray SDK version
- Python version
- Error message and stack trace
- Minimal reproduction code
- What you expected vs what happened

### Contributing

This is a take-home assignment, but the architecture is production-ready!

## Quick Reference

### SDK

```python
from xray import configure, RunContext, StepContext, StepType

# Configure
configure(api_url="http://localhost:8001", enabled=True)

# Run
with RunContext("pipeline-name") as run:
    # Step
    with StepContext("step-name", StepType.FILTER) as step:
        step.set_inputs({...})
        step.set_candidates([...])
        step.set_reasoning("Why...")

    run.set_final_output({...})
```

### API

```bash
# Health check
curl http://localhost:8001/health

# Get runs
curl http://localhost:8001/api/runs

# Get specific run
curl http://localhost:8001/api/runs/{id}

# Query steps
curl -X POST http://localhost:8001/api/steps/query \
  -d '{"step_type": "FILTER", "min_reduction_rate": 0.9}'

# Analytics
curl http://localhost:8001/api/analytics/summary
```

## What's Next?

**New users**: Start with [Getting Started](./getting-started.md)

**Experienced users**: Jump to [Best Practices](./best-practices.md)

**API users**: See [API Reference](./api-reference.md)

**Want to understand internals?**: Read [ARCHITECTURE.md](../ARCHITECTURE.md)

---

**Ready to start?** → [Getting Started Guide](./getting-started.md)
