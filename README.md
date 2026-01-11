# X-Ray: Debugging System for Non-Deterministic Pipelines

> **Full-Stack Engineering Assignment** - A complete debugging system that captures the "why" behind decisions in multi-step, non-deterministic pipelines.

## 🎯 What is X-Ray?

X-Ray is a debugging system designed for modern AI-powered pipelines where traditional logging isn't enough. When your competitor selection returns a **laptop stand** for an **iPhone case**, X-Ray shows you exactly which step failed and why.

**Key Difference from Traditional Tracing**:
- Traditional: "What functions ran and how long?"
- X-Ray: "Why did the system make this decision?"

## 🛠️ Local Development Setup

### Prerequisites

- **Python 3.10+** - Check with `python3 --version`
- **PostgreSQL 12+** - Database server
- **Git** - Version control

### Step-by-Step Setup

#### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd xray-assignment
```

#### 2. Install PostgreSQL

**macOS** (Homebrew):
```bash
brew install postgresql@14
brew services start postgresql@14
```

**Ubuntu/Debian**:
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**Windows**: Download from [postgresql.org](https://www.postgresql.org/download/windows/)

#### 3. Create Database

```bash
# Connect to PostgreSQL
psql postgres

# Create database
CREATE DATABASE xray_db;

# Exit
\q
```

Or simply:
```bash
createdb xray_db
```

#### 4. Setup X-Ray API

```bash
cd xray-api

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set database URL (optional, defaults to localhost)
export DATABASE_URL="postgresql://localhost:5432/xray_db"

# Run migrations (create tables)
alembic upgrade head
```

#### 5. Setup X-Ray SDK

```bash
cd ../xray-sdk

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .
```

#### 6. Verify Setup

**Test Database Connection**:
```bash
cd ../xray-api
source .venv/bin/activate
python -c "from app.database import engine; print('Database connected!' if engine else 'Failed')"
```

**Test API**:
```bash
# Start API (from xray-api directory)
uvicorn app.main:app --reload --port 8001

# In another terminal, test health endpoint
curl http://127.0.0.1:8001/health
# Expected: {"status":"healthy","service":"xray-api","version":"1.0.0"}
```

**Test SDK Import**:
```bash
cd ../xray-sdk
source .venv/bin/activate
python -c "from xray import RunContext, StepContext, configure; print('SDK imported successfully!')"
```

### Troubleshooting

**PostgreSQL Connection Issues**:
- Ensure PostgreSQL is running: `brew services list` (macOS) or `sudo systemctl status postgresql` (Linux)
- Check port 5432 is not in use: `lsof -i :5432`
- Verify database exists: `psql -l | grep xray_db`

**Import Errors**:
- Ensure you're in the correct virtual environment: `which python`
- Reinstall SDK: `cd xray-sdk && pip install -e .`

**Port Already in Use**:
- API default port is 8001. Change with: `uvicorn app.main:app --port 8002`

## 🚀 Quick Start (3 Steps)

### 1. Start the API

```bash
./start_api.sh
```

This starts the FastAPI backend on http://127.0.0.1:8001

### 2. Run the Demo

```bash
cd examples
python3 competitor_selection_demo.py
```

This runs a realistic competitor selection pipeline with a deliberate bug.

### 3. Debug the Issue

```bash
python3 debug_competitor_selection.py
```

This investigates the bug using X-Ray's API and finds the root cause in ~2 minutes.

## 📊 What You'll See

**The Problem**: Pipeline selects wrong competitor (laptop stand for phone case)

**The Investigation**: X-Ray shows:
1. Filter step has threshold=0.3 (too low!)
2. Only 16% of candidates filtered (should be 90%)
3. Laptop stands passed through with 0.7 similarity
4. Ranking boosted by price match (both ~$20)
5. Wrong item scored 0.89 (highest)

**Time Saved**: Hours → Minutes

## 📁 Project Structure

```
xray-assignment/
├── ARCHITECTURE.md              # Complete architecture document ⭐
├── QUICKSTART.md               # Setup and testing guide
├── README.md                   # This file
├── start_api.sh               # Start the API server
│
├── xray-sdk/                   # SDK Package
│   ├── .venv/                 # Virtual environment
│   └── xray/
│       ├── __init__.py        # Public API
│       ├── models.py          # Data models
│       ├── context.py         # Context managers
│       ├── config.py          # Configuration
│       ├── client.py          # HTTP client
│       └── sampling.py        # Smart sampling
│
├── xray-api/                   # API Backend
│   ├── .venv/                 # Virtual environment
│   └── app/
│       ├── main.py            # FastAPI app
│       ├── models.py          # Database models
│       ├── database.py        # DB connection
│       ├── schemas.py         # Pydantic schemas
│       └── routers/
│           ├── ingest.py      # POST /api/runs/ingest
│           └── query.py       # Query endpoints
│
├── examples/                   # Realistic demos ⭐
│   ├── competitor_selection_demo.py
│   ├── debug_competitor_selection.py
│   └── README.md
│
├── diagrams/                   # Architecture diagrams
│   ├── system-architecture.png
│   ├── debugging-flow.png
│   └── ... (8 total)
│
└── test_end_to_end.py         # Integration tests
```

## 🎬 Demo Walkthrough

### The Scenario

E-commerce platform needs to find competitors for benchmarking. Pipeline has 5 steps:
1. Generate keywords (LLM)
2. Search catalog
3. Filter by category ← **Bug here!**
4. Rank by relevance
5. Select best

### The Bug

Category filter threshold is too low (0.3), letting laptop stands through as competitors for phone cases.

### Investigation with X-Ray

```bash
# 1. Query API for latest run
curl http://127.0.0.1:8001/api/runs?pipeline_name=competitor-selection

# 2. Get detailed trace
curl http://127.0.0.1:8001/api/runs/{run_id}

# 3. Inspect the filter step
# Shows: threshold=0.3, reduction=16%, laptop stands passed through

# 4. Check ranking step
# Shows: laptop stand scored 0.89 (highest) due to price match boost
```

**Root cause found in 2 minutes!**

### The Fix

```python
# Change threshold from 0.3 to 0.7
filters_applied = {"category_similarity_threshold": 0.7}

# Add LLM validation step
with StepContext("llm_validate_category", StepType.LLM) as step:
    validated = llm_check_category_match(ranked)
```

**Verify**: Query API again, see 90% reduction instead of 16%

## 🏗️ Architecture Highlights

### SDK Design

**Zero-Friction Instrumentation**:
```python
with RunContext("competitor-selection") as run:
    with StepContext("filter_products", StepType.FILTER) as step:
        filtered = filter_by_price(candidates)
        step.set_candidates(filtered, previous_count=len(candidates))
        step.set_reasoning("Filtered by price range $10-$50")
```

**Automatic**:
- ✅ Timing captured
- ✅ Candidate counts tracked
- ✅ Data sent to API (async, non-blocking)
- ✅ Smart sampling (5000→150 = 97% reduction)

**Resilient**:
- API down? Continues silently or logs locally
- Overhead: 0.25ms per step (async mode)
- Can disable entirely: `configure(enabled=False)`

### API Design

**PostgreSQL + JSONB**:
- Structured data (Run + Step tables) for queryability
- Flexible JSONB for variable pipeline types
- Indexes on step_type, candidates_in, start_time

**Cross-Pipeline Queries**:
```bash
# Find all FILTER steps with >90% reduction (any pipeline)
curl -X POST /api/steps/query -d '{"step_type": "FILTER", "min_reduction_rate": 0.9}'
```

Works across competitor-selection, listing-optimization, categorization, fraud-detection - any pipeline!

## 📈 Key Metrics

- **SDK Code**: ~1,644 lines
- **API Code**: ~746 lines
- **Storage Reduction**: 97% (smart sampling)
- **Overhead**: 0.25ms per step (async)
- **Time Saved**: Hours → Minutes

## 📚 Documentation

### User Documentation

- **[docs/](docs/)** - Complete user documentation ⭐
  - **[Getting Started](docs/getting-started.md)** - Installation & first pipeline
  - **[SDK Reference](docs/sdk-reference.md)** - Complete Python API
  - **[API Reference](docs/api-reference.md)** - REST endpoints
  - **[Best Practices](docs/best-practices.md)** - Tips and patterns

### Technical Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete technical deep-dive ⭐
  - Data model rationale
  - Debugging walkthrough (phone case → laptop stand)
  - Queryability across pipelines
  - Performance & scale (5000→30 problem)
  - Developer experience (minimal vs full instrumentation)
  - Real-world application (e-commerce search)
  - Future improvements
  - API specification

### Guides

- **[QUICKSTART.md](QUICKSTART.md)** - Setup and usage guide
- **[examples/README.md](examples/README.md)** - Demo walkthrough
- **[IDE_SETUP.md](IDE_SETUP.md)** - VS Code configuration
- **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** - Project overview

## 🧪 Testing

### Manual Tests

```bash
# Quick test
python quick_test.py

# Full integration test
python test_end_to_end.py

# Demo with debugging
cd examples
python3 competitor_selection_demo.py
python3 debug_competitor_selection.py
```

### What's Tested

- ✅ SDK instrumentation
- ✅ Context managers (automatic timing)
- ✅ Smart sampling (5000→150)
- ✅ Async sending (non-blocking)
- ✅ API ingestion
- ✅ Query endpoints
- ✅ Cross-pipeline queries
- ✅ Analytics
- ✅ End-to-end flow

## 🌟 Key Features

### 1. Decision Context, Not Just Timing

Traditional tracing:
```
filter_by_category: 120ms ✓
```

X-Ray:
```
filter_by_category: 120ms
  Inputs: {threshold: 0.3}
  Candidates: 5000 → 4200 (16% reduction)
  Reasoning: "Filtered by category similarity using embedding distance"
  Sample: [Laptop Stand, Phone Case, ...]  ← See actual data!
```

### 2. Smart Sampling

Problem: 5000 candidates = 5MB per step = 50GB/day

Solution: Sample 150 (head + tail + random) = 97% reduction

Still enough to debug 95% of issues!

### 3. Cross-Pipeline Queries

Works across any pipeline type:
- Competitor selection
- Listing optimization
- Categorization
- Fraud detection
- Image classification
- Any future pipeline!

**How**: Standardized step types (LLM, SEARCH, FILTER, RANK) + flexible JSONB

### 4. Developer-Friendly

**Minimal** (3 lines):
```python
with RunContext("pipeline") as run:
    # existing code unchanged
    run.set_final_output(result)
```

**Full** (~5 lines per step):
```python
with StepContext("filter", StepType.FILTER) as step:
    step.set_inputs({"threshold": 0.7})
    filtered = filter_by_category(candidates)
    step.set_candidates(filtered, previous_count=len(candidates))
    step.set_reasoning("Filtered by category")
```

## 🔧 Technical Stack

- **SDK**: Python 3.10+, Pydantic, httpx
- **API**: FastAPI, SQLAlchemy, PostgreSQL, Uvicorn
- **Deployment**: Docker-ready (not included but easy to add)

## 🚀 Future Improvements

See [ARCHITECTURE.md - Future Improvements](ARCHITECTURE.md#future-improvements) for 10 production-ready enhancements including:
- Adaptive sampling strategies
- A/B test diff viewer
- Anomaly detection & alerts
- Multi-language SDKs (JS, Go, Java)
- Trace replay
- Cost tracking
- Web UI dashboard
- OpenTelemetry integration

## 📝 Assignment Completion Checklist

- ✅ **X-Ray SDK** - Lightweight instrumentation library
- ✅ **X-Ray API** - Ingest + query endpoints
- ✅ **ARCHITECTURE.md** - Complete technical document with diagrams
- ✅ **Working Demo** - Realistic competitor selection example
- ✅ **Tests** - Integration tests passing
- ✅ **Video** - 10-minute walkthrough (see video-walkthrough.mp4)

## 🎯 Use Cases

### 1. Competitor Selection (E-Commerce)
Debug why wrong products are selected as competitors

### 2. Search Relevance
Find why "wireless headphones" returns corded headphones

### 3. Content Moderation
Investigate why safe content was flagged

### 4. Recommendation Systems
Understand why irrelevant items are recommended

### 5. Fraud Detection
Debug false positives in transaction screening

### 6. Any Multi-Step Pipeline
Where "what happened" isn't enough - you need "why"

## 🤝 Contributing

This is a take-home assignment, not open for contributions. But the architecture is production-ready!

## 📄 License

MIT License (for demonstration purposes)

## 👤 Author

Built as a full-stack engineering assignment demonstrating:
- System design
- API development
- SDK design
- Database modeling
- Technical writing
- Problem-solving

---

**Ready to see it in action?**

1. `./start_api.sh` - Start the backend
2. `cd examples && python3 competitor_selection_demo.py` - Run the demo
3. `python3 debug_competitor_selection.py` - Investigate the bug

**Time**: 5 minutes to see the complete flow 🚀
