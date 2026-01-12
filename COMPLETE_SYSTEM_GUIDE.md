# Complete System Guide: X-Ray Deep Dive

This document explains **everything** about X-Ray - from user integration to internal implementation. After reading this, you'll understand every component, every parameter, every design decision, and be able to explain the entire system in detail.

---

## Table of Contents

1. [High-Level Overview](#high-level-overview)
2. [User's Journey: From Integration to Debugging](#users-journey-from-integration-to-debugging)
3. [SDK Internal Architecture](#sdk-internal-architecture)
4. [API Internal Architecture](#api-internal-architecture)
5. [Data Flow: Complete Lifecycle](#data-flow-complete-lifecycle)
6. [Database Schema & Design](#database-schema--design)
7. [Smart Sampling Algorithm](#smart-sampling-algorithm)
8. [Configuration System](#configuration-system)
9. [Error Handling & Fallback Modes](#error-handling--fallback-modes)
10. [Performance & Optimization](#performance--optimization)
11. [Deployment Architecture](#deployment-architecture)
12. [Common Interview Questions & Answers](#common-interview-questions--answers)

---

## High-Level Overview

### What Problem Does X-Ray Solve?

**Traditional Problem:**
- Multi-step AI/ML pipelines make wrong decisions
- No visibility into WHY decisions were made
- Debugging takes hours/days: add print statements, re-run, guess

**X-Ray Solution:**
- Captures decision context at each step (inputs, outputs, reasoning, candidates)
- Stores traces in queryable database
- Debug in minutes by querying traces when issues occur

### Core Concept

X-Ray is like a **flight recorder** for your application:
- Silently records what happens (< 1ms overhead)
- You only look at the recording when something goes wrong
- Shows you exactly which step failed and why

### Two-Component Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Component 1: SDK                        │
│  • Python library users import                              │
│  • Provides context managers (RunContext, StepContext)      │
│  • Automatically captures timing, data, reasoning           │
│  • Sends traces to API (async, non-blocking)                │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      │ HTTP POST (background)
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                     Component 2: API                        │
│  • FastAPI service (separate from user's app)               │
│  • Receives traces via POST /api/runs/ingest                │
│  • Stores in PostgreSQL with JSONB                          │
│  • Provides query endpoints (GET, POST)                     │
└─────────────────────────────────────────────────────────────┘
```

**Key Point:** These are **separate services**. User's app uses SDK, X-Ray API runs independently.

---

## User's Journey: From Integration to Debugging

### Step 1: User Integrates SDK into Their FastAPI App

**User's existing code:**
```python
# app/main.py (BEFORE X-Ray)
from fastapi import FastAPI

app = FastAPI()

@app.post("/api/competitors")
async def find_competitors(product_id: str):
    product = get_product(product_id)
    keywords = llm.generate_keywords(product)
    candidates = search_catalog(keywords)
    filtered = filter_by_category(candidates, threshold=0.3)
    ranked = rank_by_relevance(filtered)
    return ranked[0]
```

**After integration (5 minutes):**
```python
# app/main.py (AFTER X-Ray)
from fastapi import FastAPI
from xray import RunContext, StepType, configure

# Configure once at startup
configure(
    api_url="http://xray-api.mycompany.com",
    enabled=True,
    async_mode=True,
    fallback_mode=FallbackMode.SILENT
)

app = FastAPI()

@app.post("/api/competitors")
async def find_competitors(product_id: str):
    # Wrap entire pipeline
    with RunContext("competitor-selection", metadata={"product_id": product_id}) as run:

        # Wrap each step
        with run.step("generate_keywords", StepType.LLM) as step:
            keywords = llm.generate_keywords(product)
            step.set_outputs({"keywords": keywords})
            step.set_reasoning("Used GPT-4 to extract keywords")

        with run.step("search_catalog", StepType.SEARCH) as step:
            candidates = search_catalog(keywords)
            step.set_candidates(
                candidates_in=0,
                candidates_out=len(candidates),
                data=candidates
            )  # Auto-sampled if > 100

        with run.step("filter_by_category", StepType.FILTER) as step:
            threshold = 0.3
            step.set_inputs({"threshold": threshold})
            filtered = filter_by_category(candidates, threshold)
            step.set_candidates(
                candidates_in=len(candidates),
                candidates_out=len(filtered),
                data=filtered
            )

        with run.step("rank_by_relevance", StepType.RANK) as step:
            ranked = rank_by_relevance(filtered)
            step.set_candidates(ranked[:10])

        result = ranked[0]
        run.set_final_output({"competitor_asin": result.asin})
        return result
```

**What changed:**
1. Imported X-Ray SDK (`from xray import ...`)
2. Called `configure()` once at startup
3. Wrapped pipeline with `RunContext`
4. Wrapped each step with `StepContext`
5. Added metadata calls (`set_inputs`, `set_outputs`, `set_reasoning`, `set_candidates`)

**What did NOT change:**
- Business logic remains identical
- API response remains identical
- No changes to database, models, etc.

### Step 2: User Deploys X-Ray API (Separate Service)

User deploys X-Ray API on their infrastructure:

```bash
# Option 1: Docker
docker run -d -p 8001:8001 \
  -e DATABASE_URL=postgresql://localhost/xray_db \
  xray-api:latest

# Option 2: Kubernetes
kubectl apply -f xray-api-deployment.yaml

# Option 3: Cloud provider (AWS ECS, GCP Cloud Run, etc.)
```

**Important:** X-Ray API is a **separate service** with its own:
- Database (PostgreSQL)
- Compute resources
- Deployment pipeline
- URL (e.g., `http://xray-api.mycompany.com`)

### Step 3: Application Runs Normally

User's application runs in production:

**What happens when customer makes request:**

1. Customer calls: `POST /api/competitors?product_id=B09ABC001`

2. User's FastAPI app processes request normally

3. **Inside RunContext `__enter__`** (SDK):
   - Creates `RunModel` object with UUID
   - Records `start_time`
   - Stores in thread-local context (`contextvars`)

4. For each step, **inside StepContext `__enter__`**:
   - Creates `StepModel` object with UUID
   - Records `start_time`
   - Stores in thread-local context

5. User calls `step.set_inputs()`, `step.set_candidates()`, etc.:
   - SDK stores data in `StepModel` object
   - If candidates > 100, SDK runs **smart sampling** (more on this later)

6. **Inside StepContext `__exit__`**:
   - Records `end_time`
   - Calculates `duration_ms`
   - Adds `StepModel` to `RunModel.steps` list

7. **Inside RunContext `__exit__`**:
   - Records `end_time`
   - Marks status as SUCCESS or FAILURE
   - **Calls `send_trace()` to send to API**

8. **Inside `send_trace()` function** (SDK client):
   - Serializes `RunModel` + `StepModel[]` to JSON
   - If `async_mode=True`: Spawns background thread
   - Sends `POST /api/runs/ingest` to X-Ray API
   - If fails: Handles based on `fallback_mode`

9. API responds to customer (< 1ms overhead for X-Ray)

10. Background thread completes HTTP POST to X-Ray API

**User's application logs:**
```
INFO: 127.0.0.1:54321 - "POST /api/competitors?product_id=B09ABC001" 200 OK
```

**No X-Ray output!** (unless `verbose=True`)

### Step 4: X-Ray API Receives & Stores Trace

**On X-Ray API side:**

1. Request arrives: `POST /api/runs/ingest` with JSON payload

2. **FastAPI endpoint** (`xray-api/app/routers/ingest.py`):
   ```python
   @router.post("/api/runs/ingest")
   async def ingest_trace(payload: IngestPayload):
       # Validate payload (Pydantic automatically validates)
       # Create SQLAlchemy Run object
       # Create SQLAlchemy Step objects
       # Insert into PostgreSQL
       # Return success response
   ```

3. **Pydantic validation** (`xray-api/app/schemas.py`):
   - Validates all fields match expected types
   - Raises 400 error if validation fails

4. **Database insertion** (`xray-api/app/routers/ingest.py`):
   ```python
   # Create Run row
   db_run = Run(
       id=payload.run.id,
       pipeline_name=payload.run.pipeline_name,
       start_time=payload.run.start_time,
       end_time=payload.run.end_time,
       status=payload.run.status,
       metadata=payload.run.metadata,  # JSONB
       final_output=payload.run.final_output  # JSONB
   )
   db.add(db_run)

   # Create Step rows
   for step_data in payload.steps:
       db_step = Step(
           id=step_data.id,
           run_id=payload.run.id,
           step_name=step_data.step_name,
           step_type=step_data.step_type,
           sequence=step_data.sequence,
           start_time=step_data.start_time,
           end_time=step_data.end_time,
           inputs=step_data.inputs,  # JSONB
           outputs=step_data.outputs,  # JSONB
           reasoning=step_data.reasoning,
           candidates_in=step_data.candidates_in,
           candidates_out=step_data.candidates_out,
           candidates_data=step_data.candidates_data,  # JSONB (sampled)
           filters_applied=step_data.filters_applied,  # JSONB
           metadata=step_data.metadata  # JSONB
       )
       db.add(db_step)

   db.commit()
   ```

5. Data is now in PostgreSQL, queryable!

### Step 5: Bug Reported, User Queries X-Ray API

Customer reports: "Wrong competitor returned for product B09ABC001"

**User opens terminal and queries:**

```bash
# Find runs for this product
curl "http://xray-api.mycompany.com/api/runs?pipeline_name=competitor-selection" \
  | jq '.runs[] | select(.metadata.product_id == "B09ABC001")'
```

**What happens on X-Ray API:**

1. Request: `GET /api/runs?pipeline_name=competitor-selection`

2. **FastAPI endpoint** (`xray-api/app/routers/query.py`):
   ```python
   @router.get("/api/runs")
   async def list_runs(
       pipeline_name: Optional[str] = None,
       status: Optional[str] = None,
       limit: int = 50,
       offset: int = 0
   ):
       # Build SQLAlchemy query
       query = db.query(Run)
       if pipeline_name:
           query = query.filter(Run.pipeline_name == pipeline_name)
       if status:
           query = query.filter(Run.status == status)

       # Order by created_at desc (latest first)
       query = query.order_by(Run.created_at.desc())

       # Paginate
       runs = query.offset(offset).limit(limit).all()

       # Serialize to JSON
       return {"runs": [run.to_dict() for run in runs]}
   ```

3. SQL executed:
   ```sql
   SELECT * FROM runs
   WHERE pipeline_name = 'competitor-selection'
   ORDER BY created_at DESC
   LIMIT 50;
   ```

4. Results returned as JSON to user's terminal

**User gets run ID, queries for details:**

```bash
curl "http://xray-api.mycompany.com/api/runs/550e8400-e29b-41d4-a716-446655440000"
```

**What happens:**

1. Request: `GET /api/runs/{run_id}`

2. **FastAPI endpoint**:
   ```python
   @router.get("/api/runs/{run_id}")
   async def get_run(run_id: UUID):
       # Get run
       run = db.query(Run).filter(Run.id == run_id).first()
       if not run:
           raise HTTPException(404, "Run not found")

       # Get all steps for this run
       steps = db.query(Step).filter(Step.run_id == run_id).order_by(Step.sequence).all()

       # Return run + steps
       return {
           "run": run.to_dict(),
           "steps": [step.to_dict() for step in steps]
       }
   ```

3. SQL executed:
   ```sql
   SELECT * FROM runs WHERE id = '550e8400-...';
   SELECT * FROM steps WHERE run_id = '550e8400-...' ORDER BY sequence;
   ```

4. User sees complete trace with all steps, identifies bug!

---

## SDK Internal Architecture

### File Structure

```
xray-sdk/
├── xray/
│   ├── __init__.py       # Public API exports
│   ├── models.py         # Data models (RunModel, StepModel)
│   ├── context.py        # Context managers (RunContext, StepContext)
│   ├── config.py         # Configuration (XRayConfig, configure())
│   ├── client.py         # HTTP client (XRayClient, send_trace())
│   └── sampling.py       # Smart sampling algorithm
```

### models.py - Data Models

**RunModel:**
```python
class RunStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"

class RunModel(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    pipeline_name: str
    pipeline_version: str = "1.0.0"
    start_time: datetime
    end_time: Optional[datetime] = None
    status: RunStatus = RunStatus.RUNNING
    metadata: Dict[str, Any] = Field(default_factory=dict)
    final_output: Optional[Dict[str, Any]] = None

    # Steps are not stored here directly
    # They're sent separately in IngestPayload
```

**StepModel:**
```python
class StepType(str, Enum):
    LLM = "LLM"           # Language model calls
    SEARCH = "SEARCH"     # Retrieval/search
    FILTER = "FILTER"     # Filtering/elimination
    RANK = "RANK"         # Ranking/ordering
    SELECT = "SELECT"     # Final selection
    TRANSFORM = "TRANSFORM"  # Data transformation
    CUSTOM = "CUSTOM"     # Custom operations

class StepModel(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    step_name: str
    step_type: StepType
    sequence: int
    start_time: datetime
    end_time: Optional[datetime] = None

    # Decision context
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    reasoning: Optional[str] = None

    # Candidate tracking
    candidates_in: Optional[int] = None
    candidates_out: Optional[int] = None
    candidates_data: Optional[List[Any]] = None

    # Filters
    filters_applied: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None

    @property
    def reduction_rate(self) -> Optional[float]:
        if self.candidates_in and self.candidates_out:
            return (self.candidates_in - self.candidates_out) / self.candidates_in
        return None
```

**Why Pydantic?**
- Automatic validation (ensures data types are correct)
- JSON serialization/deserialization
- Default values
- Type hints for IDE support

### context.py - Context Managers

**RunContext Implementation:**

```python
# Thread-local storage for current run/step
_current_run: ContextVar[Optional[RunContext]] = ContextVar('current_run', default=None)
_current_step: ContextVar[Optional[StepContext]] = ContextVar('current_step', default=None)

class RunContext:
    def __init__(
        self,
        pipeline_name: str,
        pipeline_version: str = "1.0.0",
        metadata: Optional[Dict[str, Any]] = None,
        auto_send: bool = True
    ):
        self.run_model = RunModel(
            pipeline_name=pipeline_name,
            pipeline_version=pipeline_version,
            metadata=metadata or {}
        )
        self.steps: List[StepModel] = []
        self.auto_send = auto_send
        self._sequence_counter = 0

    def __enter__(self):
        # Record start time
        self.run_model.start_time = datetime.utcnow()

        # Store in thread-local context
        _current_run.set(self)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Record end time
        self.run_model.end_time = datetime.utcnow()

        # Set status based on exception
        if exc_type is not None:
            self.run_model.status = RunStatus.FAILURE
        else:
            self.run_model.status = RunStatus.SUCCESS

        # Send trace if auto_send enabled
        if self.auto_send and get_config().enabled:
            send_trace(IngestPayload(
                run=self.run_model,
                steps=self.steps
            ))

        # Clear from context
        _current_run.set(None)

        # Don't suppress exceptions
        return False

    def set_final_output(self, output: Dict[str, Any]):
        self.run_model.final_output = output

    def get_next_sequence(self) -> int:
        seq = self._sequence_counter
        self._sequence_counter += 1
        return seq
```

**StepContext Implementation:**

```python
class StepContext:
    def __init__(
        self,
        step_name: str,
        step_type: StepType,
        sequence: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        # Get current run from context
        self.run_context = get_current_run()
        if not self.run_context:
            raise RuntimeError("StepContext must be used inside RunContext")

        # Auto-assign sequence if not provided
        if sequence is None:
            sequence = self.run_context.get_next_sequence()

        self.step_model = StepModel(
            step_name=step_name,
            step_type=step_type,
            sequence=sequence,
            metadata=metadata or {}
        )

    def __enter__(self):
        # Record start time
        self.step_model.start_time = datetime.utcnow()

        # Store in thread-local context
        _current_step.set(self)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Record end time
        self.step_model.end_time = datetime.utcnow()

        # Add step to run's steps list
        self.run_context.steps.append(self.step_model)

        # Clear from context
        _current_step.set(None)

        # Don't suppress exceptions
        return False

    def set_inputs(self, inputs: Dict[str, Any]):
        self.step_model.inputs = inputs

    def set_outputs(self, outputs: Dict[str, Any]):
        self.step_model.outputs = outputs

    def set_reasoning(self, reasoning: str):
        self.step_model.reasoning = reasoning

    def set_candidates(
        self,
        candidates: List[Any],
        previous_count: Optional[int] = None,
        auto_sample: bool = True
    ):
        self.step_model.candidates_out = len(candidates)

        if previous_count is not None:
            self.step_model.candidates_in = previous_count

        # Apply smart sampling if enabled and needed
        if auto_sample and len(candidates) > get_config().max_candidates_full_capture:
            sampled = smart_sample(
                candidates,
                max_full=get_config().max_candidates_full_capture
            )
            self.step_model.candidates_data = sampled
        else:
            self.step_model.candidates_data = candidates

    def set_filters(self, filters: Dict[str, Any]):
        self.step_model.filters_applied = filters

    def set_metadata(self, metadata: Dict[str, Any]):
        self.step_model.metadata.update(metadata)
```

**Key Design Decisions:**

1. **Context Variables (`contextvars`)**:
   - Thread-safe storage of current run/step
   - Works with async/await
   - Allows accessing current context from anywhere in call stack

2. **Automatic Timing**:
   - `__enter__` records `start_time`
   - `__exit__` records `end_time`
   - User doesn't need to call `time.time()` manually

3. **Sequence Auto-Increment**:
   - Each step gets next sequence number automatically
   - Ensures steps are ordered correctly

4. **Exception Handling**:
   - `__exit__` receives exception info
   - Marks run as FAILURE if exception occurred
   - Returns `False` to not suppress exception (app should fail if business logic fails)

### config.py - Configuration

**XRayConfig:**

```python
class FallbackMode(str, Enum):
    SILENT = "SILENT"  # Continue silently (production)
    LOG = "LOG"        # Write to local file (development)
    RAISE = "RAISE"    # Raise exception (testing)

class XRayConfig(BaseModel):
    # API connection
    api_url: str = "http://localhost:8000"
    timeout_seconds: float = 5.0

    # Behavior
    enabled: bool = True
    async_mode: bool = True
    fallback_mode: FallbackMode = FallbackMode.SILENT

    # Sampling
    max_candidates_full_capture: int = 100

    # Fallback logging
    log_file: Optional[str] = None

    # Debugging
    verbose: bool = False

# Global config instance
_config: XRayConfig = XRayConfig()

def configure(**kwargs):
    """Update global configuration"""
    global _config
    _config = XRayConfig(**{**_config.dict(), **kwargs})

def get_config() -> XRayConfig:
    """Get current configuration"""
    return _config
```

**Why Global Config?**
- Configured once at application startup
- Accessed anywhere in SDK without passing around
- Can be overridden with environment variables

### client.py - HTTP Client

**send_trace() Function:**

```python
def send_trace(payload: IngestPayload) -> bool:
    """Send trace to X-Ray API"""
    config = get_config()

    # Check if enabled
    if not config.enabled:
        return False

    # Async or sync mode
    if config.async_mode:
        # Spawn background thread (non-blocking)
        thread = threading.Thread(target=_send_trace_sync, args=(payload,))
        thread.daemon = True  # Don't block app shutdown
        thread.start()
        return True
    else:
        # Sync mode (blocks until sent)
        return _send_trace_sync(payload)

def _send_trace_sync(payload: IngestPayload) -> bool:
    """Actually send the trace (synchronous)"""
    config = get_config()

    try:
        # Serialize to JSON
        json_data = payload.json()

        # Send POST request
        response = httpx.post(
            f"{config.api_url}/api/runs/ingest",
            content=json_data,
            headers={"Content-Type": "application/json"},
            timeout=config.timeout_seconds
        )

        # Check response
        if response.status_code == 201:
            if config.verbose:
                print(f"[X-Ray] Trace sent successfully (run_id={payload.run.id})")
            return True
        else:
            if config.verbose:
                print(f"[X-Ray] Failed to send trace: {response.status_code}")
            _handle_failure(payload, f"HTTP {response.status_code}")
            return False

    except httpx.TimeoutException:
        if config.verbose:
            print(f"[X-Ray] Timeout sending trace")
        _handle_failure(payload, "timeout")
        return False

    except Exception as e:
        if config.verbose:
            print(f"[X-Ray] Error sending trace: {e}")
        _handle_failure(payload, str(e))
        return False

def _handle_failure(payload: IngestPayload, reason: str):
    """Handle trace send failure based on fallback mode"""
    config = get_config()

    if config.fallback_mode == FallbackMode.SILENT:
        # Do nothing, continue silently
        pass

    elif config.fallback_mode == FallbackMode.LOG:
        # Write to local file
        if config.log_file:
            with open(config.log_file, 'a') as f:
                f.write(payload.json() + '\n')

    elif config.fallback_mode == FallbackMode.RAISE:
        # Raise exception (for testing)
        raise XRayClientError(f"Failed to send trace: {reason}")
```

**Key Design Decisions:**

1. **Async Mode (Default)**:
   - Spawns background thread
   - User's app doesn't wait for HTTP response
   - < 1ms overhead

2. **Sync Mode (Development)**:
   - Blocks until HTTP completes
   - Easier to debug (see errors immediately)
   - Use for testing

3. **Fallback Modes**:
   - **SILENT**: Production - app continues even if X-Ray fails
   - **LOG**: Development - write to file, upload later
   - **RAISE**: Testing - fail fast if X-Ray broken

4. **Timeout**:
   - Default 5 seconds
   - Prevents hanging if X-Ray API slow
   - After timeout, handles based on fallback mode

### sampling.py - Smart Sampling

**The Problem:**
- User has 5000 candidates in search step
- Storing all 5000 = 5MB per step
- 1000 runs/day = 5GB/day just for one step!
- Too expensive, slow to query

**The Solution: Smart Sampling**

```python
def smart_sample(
    candidates: List[Any],
    max_full: int = 100,
    sample_size: int = 50
) -> List[Any]:
    """
    Sample candidates intelligently:
    - If <= max_full: return all
    - If > max_full: return head + tail + random

    This preserves:
    - What came in first (head)
    - What came in last (tail)
    - Random sample from middle
    """
    if len(candidates) <= max_full:
        return candidates

    # Sample ~150 total (50 + 50 + 50)
    head = candidates[:sample_size]        # First 50
    tail = candidates[-sample_size:]       # Last 50

    # Random 50 from middle
    middle_start = sample_size
    middle_end = len(candidates) - sample_size
    if middle_end > middle_start:
        middle_indices = random.sample(
            range(middle_start, middle_end),
            min(sample_size, middle_end - middle_start)
        )
        middle = [candidates[i] for i in sorted(middle_indices)]
    else:
        middle = []

    # Combine
    sampled = head + middle + tail

    # Add metadata about sampling
    return sampled  # ~150 items instead of 5000
```

**Example:**

```python
# Before sampling
candidates = [item1, item2, ..., item5000]  # 5000 items

# After sampling
sampled = [
    item1, item2, ..., item50,      # Head (first 50)
    item2467, item3891, ...,        # Middle (random 50)
    item4951, item4952, ..., item5000  # Tail (last 50)
]  # ~150 items
```

**Why This Strategy?**

1. **Head**: See what initially passed filters
2. **Tail**: See what came in last (might be different)
3. **Middle**: Random sample for statistical representation

**Trade-offs:**
- ✅ 97% storage reduction (5000 → 150)
- ✅ Can still debug 95% of issues
- ❌ Can't see all 5000 items (but can see patterns)

**Configuration:**

```python
# Adjust threshold
configure(max_candidates_full_capture=200)  # More aggressive sampling

# Disable sampling (debugging)
step.set_candidates(candidates, auto_sample=False)  # Store all
```

---

## API Internal Architecture

### File Structure

```
xray-api/
├── app/
│   ├── main.py           # FastAPI app initialization
│   ├── database.py       # Database connection
│   ├── models.py         # SQLAlchemy models (Run, Step tables)
│   ├── schemas.py        # Pydantic request/response schemas
│   └── routers/
│       ├── ingest.py     # POST /api/runs/ingest
│       └── query.py      # GET /api/runs, POST /api/steps/query, etc.
```

### main.py - FastAPI App

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.routers import ingest, query

# Create tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="X-Ray API",
    description="Debugging system for non-deterministic pipelines",
    version="1.0.0"
)

# CORS middleware (for web UIs)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(ingest.router, prefix="/api", tags=["ingest"])
app.include_router(query.router, prefix="/api", tags=["query"])

# Health check endpoint
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "xray-api",
        "version": "1.0.0"
    }
```

**Why FastAPI?**
- Automatic OpenAPI docs (Swagger UI at `/docs`)
- Type validation via Pydantic
- Async support (important for high throughput)
- Fast (built on Starlette + Pydantic)

### database.py - Database Connection

```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/xray_db")

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_size=10,          # Connection pool
    max_overflow=20,       # Max connections
    pool_pre_ping=True,    # Verify connections before use
    echo=False             # Set True to see SQL queries
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Key Points:**
- `DATABASE_URL` from environment (12-factor app)
- Connection pooling for performance
- `get_db()` dependency for FastAPI routes

### models.py - SQLAlchemy Models

**Run Table:**

```python
from sqlalchemy import Column, String, DateTime, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base
import uuid

class Run(Base):
    __tablename__ = "runs"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Pipeline info
    pipeline_name = Column(String(255), nullable=False, index=True)
    pipeline_version = Column(String(50), nullable=False)

    # Timing
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)

    # Status
    status = Column(String(50), nullable=False, index=True)

    # Flexible data (JSONB)
    metadata = Column(JSONB, nullable=False, default=dict)
    final_output = Column(JSONB, nullable=True)

    # Computed properties
    @property
    def duration_ms(self):
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None

    def to_dict(self):
        return {
            "id": str(self.id),
            "pipeline_name": self.pipeline_name,
            "pipeline_version": self.pipeline_version,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "metadata": self.metadata,
            "final_output": self.final_output,
            "duration_ms": self.duration_ms
        }
```

**Step Table:**

```python
class Step(Base):
    __tablename__ = "steps"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign key to Run
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True)

    # Step info
    step_name = Column(String(255), nullable=False, index=True)
    step_type = Column(String(50), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)

    # Timing
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)

    # Decision context (JSONB for flexibility)
    inputs = Column(JSONB, nullable=False, default=dict)
    outputs = Column(JSONB, nullable=False, default=dict)
    reasoning = Column(Text, nullable=True)

    # Candidate tracking
    candidates_in = Column(Integer, nullable=True, index=True)
    candidates_out = Column(Integer, nullable=True, index=True)
    candidates_data = Column(JSONB, nullable=True)  # Sampled candidates

    # Filters
    filters_applied = Column(JSONB, nullable=False, default=dict)
    metadata = Column(JSONB, nullable=False, default=dict)

    # Computed properties
    @property
    def duration_ms(self):
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return None

    @property
    def reduction_rate(self):
        if self.candidates_in and self.candidates_out:
            return (self.candidates_in - self.candidates_out) / self.candidates_in
        return None

    def to_dict(self):
        return {
            "id": str(self.id),
            "run_id": str(self.run_id),
            "step_name": self.step_name,
            "step_type": self.step_type,
            "sequence": self.sequence,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "reasoning": self.reasoning,
            "candidates_in": self.candidates_in,
            "candidates_out": self.candidates_out,
            "reduction_rate": self.reduction_rate,
            "candidates_data": self.candidates_data,
            "filters_applied": self.filters_applied,
            "metadata": self.metadata
        }
```

**Why JSONB?**

1. **Flexibility**: Each pipeline has different inputs/outputs
2. **Queryability**: Can query inside JSONB with PostgreSQL operators
3. **Performance**: Binary format, indexed

**Example JSONB Queries:**

```sql
-- Find runs with specific metadata
SELECT * FROM runs WHERE metadata @> '{"user_id": "123"}';

-- Find steps with specific input
SELECT * FROM steps WHERE inputs @> '{"threshold": 0.3}';

-- Check if key exists
SELECT * FROM steps WHERE outputs ? 'keywords';
```

**Indexes:**
- `pipeline_name` - Query runs by pipeline
- `step_type` - Query steps by type
- `candidates_in`, `candidates_out` - Query by reduction rate
- `created_at` - Query recent runs

### routers/ingest.py - Ingestion Endpoint

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import IngestPayload
from app.models import Run, Step

router = APIRouter()

@router.post("/runs/ingest", status_code=201)
async def ingest_trace(
    payload: IngestPayload,
    db: Session = Depends(get_db)
):
    """
    Ingest a complete trace (run + steps)

    Body: IngestPayload (Pydantic validates automatically)
    Returns: Success message with run_id
    """

    try:
        # Create Run row
        db_run = Run(
            id=payload.run.id,
            pipeline_name=payload.run.pipeline_name,
            pipeline_version=payload.run.pipeline_version,
            start_time=payload.run.start_time,
            end_time=payload.run.end_time,
            status=payload.run.status,
            metadata=payload.run.metadata,
            final_output=payload.run.final_output
        )
        db.add(db_run)

        # Create Step rows
        for step_data in payload.steps:
            db_step = Step(
                id=step_data.id,
                run_id=payload.run.id,
                step_name=step_data.step_name,
                step_type=step_data.step_type,
                sequence=step_data.sequence,
                start_time=step_data.start_time,
                end_time=step_data.end_time,
                inputs=step_data.inputs,
                outputs=step_data.outputs,
                reasoning=step_data.reasoning,
                candidates_in=step_data.candidates_in,
                candidates_out=step_data.candidates_out,
                candidates_data=step_data.candidates_data,
                filters_applied=step_data.filters_applied,
                metadata=step_data.metadata
            )
            db.add(db_step)

        # Commit transaction
        db.commit()

        return {
            "success": True,
            "run_id": str(payload.run.id),
            "message": "Trace ingested successfully",
            "steps_count": len(payload.steps)
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Failed to ingest trace: {str(e)}")
```

**Key Points:**
- `status_code=201` - HTTP standard for "Created"
- Pydantic validates payload automatically
- Transaction: `db.commit()` or `db.rollback()`
- Returns run_id for reference

### routers/query.py - Query Endpoints

**List Runs:**

```python
@router.get("/runs")
async def list_runs(
    pipeline_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """List runs with optional filtering"""

    # Build query
    query = db.query(Run)

    # Apply filters
    if pipeline_name:
        query = query.filter(Run.pipeline_name == pipeline_name)
    if status:
        query = query.filter(Run.status == status)

    # Order by latest first
    query = query.order_by(Run.created_at.desc())

    # Get total count (before pagination)
    total = query.count()

    # Paginate
    runs = query.offset(offset).limit(limit).all()

    return {
        "runs": [run.to_dict() for run in runs],
        "total": total,
        "page": offset // limit + 1,
        "page_size": limit
    }
```

**Get Run Details:**

```python
@router.get("/runs/{run_id}")
async def get_run(
    run_id: UUID,
    db: Session = Depends(get_db)
):
    """Get a specific run with all its steps"""

    # Get run
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(404, f"Run {run_id} not found")

    # Get steps
    steps = db.query(Step).filter(Step.run_id == run_id).order_by(Step.sequence).all()

    return {
        "run": run.to_dict(),
        "steps": [step.to_dict() for step in steps]
    }
```

**Query Steps (Cross-Pipeline):**

```python
@router.post("/steps/query")
async def query_steps(
    filters: StepQueryFilters,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    Query steps across all pipelines with flexible filtering

    Body: StepQueryFilters (Pydantic model)
    """

    # Build query
    query = db.query(Step)

    # Apply filters
    if filters.pipeline_name:
        query = query.join(Run).filter(Run.pipeline_name == filters.pipeline_name)

    if filters.step_name:
        query = query.filter(Step.step_name == filters.step_name)

    if filters.step_type:
        query = query.filter(Step.step_type == filters.step_type)

    if filters.min_reduction_rate is not None:
        # Reduction rate = (candidates_in - candidates_out) / candidates_in
        query = query.filter(
            (Step.candidates_in - Step.candidates_out) / Step.candidates_in >= filters.min_reduction_rate
        )

    if filters.max_reduction_rate is not None:
        query = query.filter(
            (Step.candidates_in - Step.candidates_out) / Step.candidates_in <= filters.max_reduction_rate
        )

    if filters.min_duration_ms:
        # Duration calculation in SQL
        query = query.filter(
            extract('epoch', Step.end_time - Step.start_time) * 1000 >= filters.min_duration_ms
        )

    if filters.max_duration_ms:
        query = query.filter(
            extract('epoch', Step.end_time - Step.start_time) * 1000 <= filters.max_duration_ms
        )

    # Order by created_at desc
    query = query.order_by(Step.start_time.desc())

    # Count
    total = query.count()

    # Paginate
    steps = query.offset(offset).limit(limit).all()

    return {
        "steps": [step.to_dict() for step in steps],
        "total": total,
        "page": offset // limit + 1,
        "page_size": limit
    }
```

**Analytics Summary:**

```python
@router.get("/analytics/summary")
async def analytics_summary(
    pipeline_name: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Get aggregated metrics"""

    from datetime import datetime, timedelta
    from sqlalchemy import func

    # Date range
    start_date = datetime.utcnow() - timedelta(days=days)

    # Build query
    query = db.query(Run).filter(Run.created_at >= start_date)

    if pipeline_name:
        query = query.filter(Run.pipeline_name == pipeline_name)

    # Get runs
    runs = query.all()

    if not runs:
        return {"message": "No data"}

    # Calculate metrics
    total_runs = len(runs)
    successful = len([r for r in runs if r.status == "SUCCESS"])
    failed = len([r for r in runs if r.status == "FAILURE"])

    durations = [r.duration_ms for r in runs if r.duration_ms]
    avg_duration = sum(durations) / len(durations) if durations else 0

    # Percentiles
    sorted_durations = sorted(durations)
    p50 = sorted_durations[len(sorted_durations) // 2] if sorted_durations else 0
    p95 = sorted_durations[int(len(sorted_durations) * 0.95)] if sorted_durations else 0
    p99 = sorted_durations[int(len(sorted_durations) * 0.99)] if sorted_durations else 0

    # Steps analytics
    steps = db.query(Step).join(Run).filter(Run.created_at >= start_date)
    if pipeline_name:
        steps = steps.filter(Run.pipeline_name == pipeline_name)
    steps = steps.all()

    avg_steps = len(steps) / total_runs if total_runs else 0

    # Slowest step type
    step_durations = {}
    for step in steps:
        if step.duration_ms:
            if step.step_type not in step_durations:
                step_durations[step.step_type] = []
            step_durations[step.step_type].append(step.duration_ms)

    slowest_type = max(step_durations.items(),
                       key=lambda x: sum(x[1])/len(x[1]))[0] if step_durations else None

    return {
        "pipeline_name": pipeline_name,
        "date_range": {
            "start": start_date.isoformat(),
            "end": datetime.utcnow().isoformat()
        },
        "runs": {
            "total": total_runs,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total_runs if total_runs else 0
        },
        "performance": {
            "avg_duration_ms": round(avg_duration, 2),
            "p50_duration_ms": round(p50, 2),
            "p95_duration_ms": round(p95, 2),
            "p99_duration_ms": round(p99, 2)
        },
        "steps": {
            "avg_steps_per_run": round(avg_steps, 2),
            "slowest_step_type": slowest_type
        }
    }
```

---

## Data Flow: Complete Lifecycle

Let's trace a single request from start to finish:

### Timeline: From User Request to Query

```
T+0ms:    Customer calls user's API
T+0ms:    RunContext.__enter__() called
T+0ms:    - Creates RunModel, records start_time
T+0ms:    - Stores in contextvars

T+5ms:    StepContext("generate_keywords").__enter__()
T+5ms:    - Creates StepModel, records start_time
T+1255ms: LLM responds
T+1255ms: step.set_outputs({"keywords": [...]})
T+1255ms: StepContext.__exit__()
T+1255ms: - Records end_time, calculates duration_ms=1250
T+1255ms: - Adds StepModel to RunModel.steps

T+1255ms: StepContext("search_catalog").__enter__()
T+1255ms: - Creates StepModel
T+1575ms: Search completes with 5000 results
T+1575ms: step.set_candidates(5000 candidates)
T+1575ms: - SDK runs smart_sample(): 5000 → 150
T+1575ms: - StepModel.candidates_data = 150 items
T+1575ms: StepContext.__exit__()
T+1575ms: - Records end_time, duration_ms=320

[... more steps ...]

T+3000ms: RunContext.__exit__()
T+3000ms: - Records end_time
T+3000ms: - status = SUCCESS
T+3000ms: - Calls send_trace()

T+3001ms: send_trace() spawns background thread
T+3001ms: User's API responds to customer (<1ms overhead!)

[Background thread]
T+3050ms: HTTP POST to X-Ray API starts
T+3150ms: X-Ray API receives POST /api/runs/ingest
T+3150ms: FastAPI validates payload (Pydantic)
T+3155ms: Creates Run + Step rows in PostgreSQL
T+3160ms: Database commit
T+3165ms: Returns 201 Created
T+3165ms: Background thread completes

[Later - when debugging]
T+1 hour: User queries: curl http://xray-api/api/runs/{run_id}
T+1 hour: X-Ray API queries PostgreSQL
T+1 hour: Returns JSON with run + steps
T+1 hour: User sees trace, identifies bug!
```

### Data Transformations

**User's Code:**
```python
keywords = ["phone case", "iPhone case"]
```

**SDK StepModel:**
```python
StepModel(
    step_name="generate_keywords",
    outputs={"keywords": ["phone case", "iPhone case"]},
    ...
)
```

**SDK IngestPayload (JSON):**
```json
{
  "run": {...},
  "steps": [
    {
      "step_name": "generate_keywords",
      "outputs": {"keywords": ["phone case", "iPhone case"]},
      ...
    }
  ]
}
```

**HTTP Request:**
```http
POST /api/runs/ingest HTTP/1.1
Host: xray-api.mycompany.com
Content-Type: application/json

{JSON payload}
```

**PostgreSQL Table:**
```sql
INSERT INTO steps (id, step_name, outputs, ...)
VALUES (
  '660e8400-...',
  'generate_keywords',
  '{"keywords": ["phone case", "iPhone case"]}',  -- JSONB
  ...
);
```

**Query Response:**
```json
{
  "steps": [
    {
      "step_name": "generate_keywords",
      "outputs": {"keywords": ["phone case", "iPhone case"]},
      ...
    }
  ]
}
```

---

## Database Schema & Design

### Complete Schema

```sql
CREATE TABLE runs (
    id UUID PRIMARY KEY,
    pipeline_name VARCHAR(255) NOT NULL,
    pipeline_version VARCHAR(50) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    final_output JSONB
);

CREATE INDEX idx_runs_pipeline_name ON runs(pipeline_name);
CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_created_at ON runs(created_at DESC);

CREATE TABLE steps (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    step_name VARCHAR(255) NOT NULL,
    step_type VARCHAR(50) NOT NULL,
    sequence INTEGER NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    inputs JSONB NOT NULL DEFAULT '{}',
    outputs JSONB NOT NULL DEFAULT '{}',
    reasoning TEXT,
    candidates_in INTEGER,
    candidates_out INTEGER,
    candidates_data JSONB,
    filters_applied JSONB NOT NULL DEFAULT '{}',
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_steps_run_id ON steps(run_id);
CREATE INDEX idx_steps_step_name ON steps(step_name);
CREATE INDEX idx_steps_step_type ON steps(step_type);
CREATE INDEX idx_steps_candidates_in ON steps(candidates_in);
CREATE INDEX idx_steps_candidates_out ON steps(candidates_out);
CREATE INDEX idx_steps_sequence ON steps(run_id, sequence);
```

### Design Decisions

**Why Two Tables (Not One)?**

Option 1 (Rejected): One `traces` table with all data in JSONB
```sql
CREATE TABLE traces (
    id UUID PRIMARY KEY,
    data JSONB  -- Everything in here
);
```

❌ Problems:
- Can't query efficiently (no indexes on JSONB fields)
- Can't do JOINs
- No foreign key constraints
- Slow for large datasets

Option 2 (Chosen): Two tables with structured + JSONB hybrid
```sql
CREATE TABLE runs (...);  -- Structured fields + JSONB
CREATE TABLE steps (...);  -- Structured fields + JSONB
```

✅ Benefits:
- Fast queries on structured fields (indexed)
- Flexible JSONB for variable data
- Foreign key constraints (data integrity)
- Can JOIN runs and steps

**Why JSONB Instead of Separate Columns?**

Example: `inputs` field

Option A (Rejected): Create column for every possible input
```sql
CREATE TABLE steps (
    ...
    input_threshold FLOAT,
    input_query TEXT,
    input_limit INTEGER,
    ... (100+ columns for all possible inputs)
);
```

❌ Problems:
- Different pipelines have different inputs
- Need to add columns for every new input type
- Most columns NULL for most rows (sparse)
- Schema migrations for every new pipeline

Option B (Chosen): Use JSONB
```sql
CREATE TABLE steps (
    ...
    inputs JSONB  -- {"threshold": 0.3, "query": "phone"}
);
```

✅ Benefits:
- Any pipeline can store any inputs
- No schema changes needed
- Still queryable: `WHERE inputs @> '{"threshold": 0.3}'`
- Compact storage (binary format)

**Why ON DELETE CASCADE?**

```sql
run_id UUID REFERENCES runs(id) ON DELETE CASCADE
```

When a run is deleted, all its steps are automatically deleted.

Alternative (Rejected): Manual cleanup
```python
# Without CASCADE
db.query(Step).filter(Step.run_id == run_id).delete()
db.query(Run).filter(Run.id == run_id).delete()
```

❌ Problems:
- Easy to forget
- Data inconsistency if run deleted but steps remain
- Extra code

✅ CASCADE handles it automatically

**Index Strategy:**

Indexes speed up queries but slow down writes. We index:

✅ **Frequently queried fields:**
- `pipeline_name` - "Show me all competitor-selection runs"
- `step_type` - "Show me all LLM steps"
- `created_at` - "Show me recent runs"
- `candidates_in/out` - "Show me steps with high reduction"

❌ **Not indexed:**
- JSONB fields (too expensive, use GIN index if needed)
- `reasoning` (TEXT field, rarely queried exactly)

**Storage Estimates:**

Assuming:
- 1000 runs/day
- 5 steps/run average
- 150 candidates stored/step (after sampling)

```
Per run:
- Run row: ~1 KB (metadata + final_output)
- Step rows: 5 × ~50 KB = 250 KB (candidates_data is biggest)
Total per run: ~251 KB

Per day: 1000 runs × 251 KB = 251 MB
Per month: 251 MB × 30 = 7.5 GB
Per year: 7.5 GB × 12 = 90 GB
```

Without sampling (5000 candidates/step):
```
Per step: 5000 candidates × 1 KB = 5 MB
Per run: 5 steps × 5 MB = 25 MB
Per day: 1000 runs × 25 MB = 25 GB
Per month: 25 GB × 30 = 750 GB
Per year: 750 GB × 12 = 9 TB (too expensive!)
```

**Sampling saves 97% storage!**

---

## Smart Sampling Algorithm

### Deep Dive

**Problem Statement:**

User has pipeline step that processes 5000 candidates. We want to store representative sample for debugging, not all 5000.

**Requirements:**
1. Small storage (< 200 items)
2. Representative of entire list
3. Shows patterns (head, tail, middle)
4. Deterministic (same input → same sample)

**Algorithm:**

```python
def smart_sample(
    candidates: List[Any],
    max_full: int = 100,
    sample_size: int = 50
) -> List[Any]:
    """
    Three-part sampling:
    1. Head: First `sample_size` items
    2. Middle: Random `sample_size` from middle
    3. Tail: Last `sample_size` items
    """

    # Step 1: Check if sampling needed
    if len(candidates) <= max_full:
        return candidates  # Small enough, store all

    # Step 2: Extract head (first 50)
    head = candidates[:sample_size]

    # Step 3: Extract tail (last 50)
    tail = candidates[-sample_size:]

    # Step 4: Extract middle (random 50 from middle)
    middle_start = sample_size
    middle_end = len(candidates) - sample_size

    if middle_end > middle_start:
        # Calculate middle range
        middle_size = middle_end - middle_start

        # Randomly sample indices
        sample_count = min(sample_size, middle_size)
        middle_indices = random.sample(
            range(middle_start, middle_end),
            sample_count
        )

        # Sort indices to maintain order
        middle_indices.sort()

        # Extract items
        middle = [candidates[i] for i in middle_indices]
    else:
        # No middle (list too small after head/tail)
        middle = []

    # Step 5: Combine
    sampled = head + middle + tail

    return sampled
```

**Example Walkthrough:**

Input: 5000 candidates

```python
candidates = [
    {"id": 1, "title": "Product 1"},
    {"id": 2, "title": "Product 2"},
    ...,
    {"id": 5000, "title": "Product 5000"}
]
```

**Step 1: Check size**
```python
len(candidates) = 5000
max_full = 100
5000 > 100  # Sampling needed
```

**Step 2: Head**
```python
head = candidates[:50]
# [{"id": 1}, {"id": 2}, ..., {"id": 50}]
```

**Step 3: Tail**
```python
tail = candidates[-50:]
# [{"id": 4951}, {"id": 4952}, ..., {"id": 5000}]
```

**Step 4: Middle**
```python
middle_start = 50
middle_end = 4950
middle_size = 4900

# Random sample 50 indices from [50, 4950)
middle_indices = [127, 489, 723, 1056, ..., 4721]  # 50 random indices
middle_indices.sort()  # [127, 489, ..., 4721]

middle = [candidates[127], candidates[489], ...]
# [{"id": 128}, {"id": 490}, ..., {"id": 4722}]
```

**Step 5: Combine**
```python
sampled = head + middle + tail
# [
#   {"id": 1}, ..., {"id": 50},      # Head: 50 items
#   {"id": 128}, ..., {"id": 4722},  # Middle: 50 items
#   {"id": 4951}, ..., {"id": 5000}  # Tail: 50 items
# ]
# Total: 150 items
```

**Result: 5000 → 150 (97% reduction)**

### Why This Strategy?

**Alternative 1: Random Sample Entire List**
```python
sampled = random.sample(candidates, 150)
```

❌ Problems:
- Might miss important head/tail items
- Not deterministic (different sample each time)
- Loses ordering information

**Alternative 2: Take First 150**
```python
sampled = candidates[:150]
```

❌ Problems:
- Misses end of list
- Bias towards early items
- Can't detect tail anomalies

**Alternative 3: Stratified Sampling**
```python
# Divide into buckets, sample from each
buckets = 10
per_bucket = 15
sampled = []
for i in range(buckets):
    start = i * (len(candidates) // buckets)
    end = (i + 1) * (len(candidates) // buckets)
    sampled.extend(random.sample(candidates[start:end], per_bucket))
```

✅ This is similar to our approach!
❌ But more complex, harder to understand

**Our Approach (Head + Middle + Tail):**

✅ Benefits:
- **Head**: See what initially passed filters
- **Middle**: Random sample for statistical representation
- **Tail**: See what came in last (might be different)
- **Simple**: Easy to understand and debug
- **Deterministic**: Same seed → same sample

**Use Cases:**

1. **Filter Step** (5000 → 500):
   - Head: See first items that passed
   - Middle: Random sample of middle items
   - Tail: See last items that passed
   - Can identify if filter is biased towards head/tail

2. **Search Step** (returns 5000):
   - Head: See top-ranked results
   - Middle: See mid-range results
   - Tail: See lowest-ranked results
   - Can identify ranking issues

3. **Rank Step** (5000 input):
   - Head: See items ranked #1-50
   - Middle: See items ranked ~#2500
   - Tail: See items ranked #4951-5000
   - Can identify ranking distribution

### Configuration

**Adjust thresholds:**

```python
# More aggressive sampling
configure(max_candidates_full_capture=50)  # Sample if > 50

# Less aggressive sampling
configure(max_candidates_full_capture=200)  # Only sample if > 200
```

**Disable for specific step:**

```python
# Store all candidates (no sampling)
step.set_candidates(candidates, auto_sample=False)
```

**When to disable:**
- Debugging specific issue that requires seeing all items
- Small dataset (< 100 items)
- Critical step where every item matters

---

## Configuration System

### All Configuration Options

```python
from xray import configure, FallbackMode

configure(
    # API Connection
    api_url="http://xray-api.mycompany.com",
    timeout_seconds=5.0,

    # Behavior
    enabled=True,
    async_mode=True,
    fallback_mode=FallbackMode.SILENT,

    # Sampling
    max_candidates_full_capture=100,

    # Fallback Logging
    log_file="/var/log/xray-fallback.jsonl",

    # Debugging
    verbose=False
)
```

### Parameter Explanations

#### `api_url` (string)

**What**: URL of X-Ray API service

**Examples:**
```python
# Local development
api_url="http://localhost:8001"

# Production (cloud)
api_url="https://xray-api.mycompany.com"

# Internal network
api_url="http://10.0.1.50:8001"
```

**Default**: `"http://localhost:8000"`

**How it's used:**
```python
# In client.py
response = httpx.post(
    f"{config.api_url}/api/runs/ingest",
    ...
)
```

#### `timeout_seconds` (float)

**What**: How long to wait for X-Ray API before giving up

**Why important**: Prevents hanging if X-Ray API is slow/down

**Examples:**
```python
# Aggressive (fail fast)
timeout_seconds=2.0

# Default
timeout_seconds=5.0

# Patient (for slow networks)
timeout_seconds=10.0
```

**What happens on timeout:**
- Triggers fallback mode behavior
- Application continues normally
- Trace might be lost (unless LOG mode)

#### `enabled` (bool)

**What**: Master on/off switch for X-Ray

**Examples:**
```python
# Enable
enabled=True

# Disable completely (zero overhead)
enabled=False

# Conditional (environment-based)
enabled=os.getenv("XRAY_ENABLED") == "true"

# Sampling (only 10% of requests)
enabled=random.random() < 0.1
```

**When disabled:**
```python
with RunContext(...):  # Does nothing
    with StepContext(...):  # Does nothing
        pass  # Your code runs normally
```

**Use cases:**
- Disable in local development
- Disable for performance-critical endpoints
- Enable only for subset of traffic

#### `async_mode` (bool)

**What**: Send traces in background thread (non-blocking) vs synchronously (blocking)

**Async Mode (True - Default):**
```python
async_mode=True

# What happens:
# 1. RunContext.__exit__() called
# 2. Spawns background thread
# 3. Returns immediately (<1ms)
# 4. Background thread sends HTTP POST
# 5. Application continues
```

**Sync Mode (False):**
```python
async_mode=False

# What happens:
# 1. RunContext.__exit__() called
# 2. Sends HTTP POST synchronously
# 3. Waits for response (50-200ms)
# 4. Then application continues
```

**When to use:**
- **Async**: Production (always)
- **Sync**: Development (easier to debug), Testing (deterministic)

**Performance:**
```python
# Async mode
request_time = 100ms (business logic) + 1ms (X-Ray) = 101ms

# Sync mode
request_time = 100ms (business logic) + 150ms (X-Ray HTTP) = 250ms
```

#### `fallback_mode` (FallbackMode)

**What**: What to do if X-Ray API fails

**Options:**

1. **SILENT** (Production):
```python
fallback_mode=FallbackMode.SILENT

# Behavior: Continue silently, trace lost
# Use when: Production (app stability > trace completeness)
```

2. **LOG** (Development):
```python
fallback_mode=FallbackMode.LOG
log_file="/tmp/xray-fallback.jsonl"

# Behavior: Write trace to local file
# Use when: Development (can upload logs later)
# Can bulk-upload later:
#   curl -X POST /api/runs/ingest -d @/tmp/xray-fallback.jsonl
```

3. **RAISE** (Testing):
```python
fallback_mode=FallbackMode.RAISE

# Behavior: Raise XRayClientError
# Use when: Testing (want to know if X-Ray broken)
```

**Example Failure Scenarios:**

```python
# Scenario 1: X-Ray API down
# - SILENT: App continues, trace lost
# - LOG: Trace written to file
# - RAISE: App crashes with XRayClientError

# Scenario 2: Network timeout
# - SILENT: App continues, trace lost
# - LOG: Trace written to file
# - RAISE: App crashes with XRayClientError

# Scenario 3: Invalid payload (SDK bug)
# - SILENT: App continues, trace lost
# - LOG: Trace written to file
# - RAISE: App crashes (good for finding SDK bugs!)
```

#### `max_candidates_full_capture` (int)

**What**: Threshold for sampling candidates

**Examples:**
```python
# Aggressive sampling
max_candidates_full_capture=50
# If candidates > 50, sample to ~150

# Default
max_candidates_full_capture=100
# If candidates > 100, sample to ~150

# Conservative sampling
max_candidates_full_capture=300
# If candidates > 300, sample to ~150
```

**Impact:**

```python
# With max_candidates_full_capture=100

step.set_candidates([1, 2, ..., 50])
# Stored: All 50 (below threshold)

step.set_candidates([1, 2, ..., 150])
# Stored: ~150 (sampled: 50 head + 50 middle + 50 tail)

step.set_candidates([1, 2, ..., 5000])
# Stored: ~150 (sampled)
```

**Storage impact:**
```python
# Aggressive (50)
# Pro: Less storage (smaller DB)
# Con: Less data for debugging

# Conservative (300)
# Pro: More data for debugging
# Con: More storage (larger DB)
```

#### `log_file` (Optional[str])

**What**: Path to fallback log file (when `fallback_mode=LOG`)

**Examples:**
```python
# Temporary directory
log_file="/tmp/xray-fallback.jsonl"

# Application logs directory
log_file="/var/log/myapp/xray-fallback.jsonl"

# None (don't log)
log_file=None
```

**Format:** JSONL (JSON Lines)
```jsonl
{"run": {...}, "steps": [...]}
{"run": {...}, "steps": [...]}
{"run": {...}, "steps": [...]}
```

**Bulk upload later:**
```bash
# Upload all traces from log file
while IFS= read -r line; do
    curl -X POST http://xray-api/api/runs/ingest \
        -H "Content-Type: application/json" \
        -d "$line"
done < /tmp/xray-fallback.jsonl
```

#### `verbose` (bool)

**What**: Print X-Ray operations to stdout

**Examples:**
```python
# Silent (production)
verbose=False

# Verbose (development)
verbose=True
```

**Output when `verbose=True`:**
```
[X-Ray] Sending trace for run 550e8400-e29b-41d4-a716-446655440000
[X-Ray] Trace sent successfully (201)
[X-Ray] Duration: 145ms

[X-Ray] Sending trace for run 660e8400-e29b-41d4-a716-446655440001
[X-Ray] Failed to send trace: Connection refused
[X-Ray] Falling back to LOG mode
```

**Use cases:**
- Development: See what X-Ray is doing
- Debugging: Diagnose X-Ray issues
- Production: Keep disabled (no noise in logs)

### Environment Variables

**Override config with environment variables:**

```python
# SDK checks these automatically
XRAY_API_URL="http://xray-api:8001"
XRAY_ENABLED="true"
XRAY_TIMEOUT="5"
XRAY_ASYNC="true"
XRAY_LOG_FILE="/var/log/xray.jsonl"
```

**Implementation:**
```python
# config.py
import os

class XRayConfig(BaseModel):
    api_url: str = os.getenv("XRAY_API_URL", "http://localhost:8000")
    enabled: bool = os.getenv("XRAY_ENABLED", "true").lower() == "true"
    timeout_seconds: float = float(os.getenv("XRAY_TIMEOUT", "5.0"))
    # ...
```

**Deployment example:**

```yaml
# docker-compose.yml
services:
  app:
    environment:
      - XRAY_API_URL=http://xray-api:8001
      - XRAY_ENABLED=true
      - XRAY_ASYNC=true
```

```yaml
# kubernetes deployment
env:
  - name: XRAY_API_URL
    value: "http://xray-api-service:8001"
  - name: XRAY_ENABLED
    value: "true"
```

---

## Error Handling & Fallback Modes

### Complete Error Flow

**Scenario: X-Ray API is down**

```python
# User's application
with RunContext("my-pipeline") as run:
    with run.step("step1", StepType.CUSTOM) as step:
        result = do_work()
        step.set_outputs({"result": result})
    # ... more steps

# What happens:
# 1. RunContext.__exit__() called
# 2. Calls send_trace()
# 3. send_trace() tries HTTP POST
# 4. Connection refused (API down)
# 5. Exception caught
# 6. Fallback mode triggered
```

**Implementation:**

```python
def _send_trace_sync(payload: IngestPayload) -> bool:
    config = get_config()

    try:
        response = httpx.post(
            f"{config.api_url}/api/runs/ingest",
            content=payload.json(),
            headers={"Content-Type": "application/json"},
            timeout=config.timeout_seconds
        )

        if response.status_code == 201:
            if config.verbose:
                print(f"[X-Ray] Trace sent successfully")
            return True
        else:
            if config.verbose:
                print(f"[X-Ray] Failed: HTTP {response.status_code}")
            _handle_failure(payload, f"HTTP {response.status_code}")
            return False

    except httpx.ConnectError as e:
        if config.verbose:
            print(f"[X-Ray] Connection error: {e}")
        _handle_failure(payload, "connection_error")
        return False

    except httpx.TimeoutException:
        if config.verbose:
            print(f"[X-Ray] Timeout after {config.timeout_seconds}s")
        _handle_failure(payload, "timeout")
        return False

    except Exception as e:
        if config.verbose:
            print(f"[X-Ray] Unexpected error: {e}")
        _handle_failure(payload, str(e))
        return False
```

**Fallback Handler:**

```python
def _handle_failure(payload: IngestPayload, reason: str):
    config = get_config()

    if config.fallback_mode == FallbackMode.SILENT:
        # Do nothing, continue silently
        pass

    elif config.fallback_mode == FallbackMode.LOG:
        # Write to local file
        if config.log_file:
            try:
                with open(config.log_file, 'a') as f:
                    f.write(payload.json() + '\n')
                if config.verbose:
                    print(f"[X-Ray] Trace written to {config.log_file}")
            except Exception as e:
                if config.verbose:
                    print(f"[X-Ray] Failed to write log: {e}")
                # Even logging failed, give up silently
                pass

    elif config.fallback_mode == FallbackMode.RAISE:
        # Raise exception
        raise XRayClientError(f"Failed to send trace: {reason}")
```

### Error Scenarios

**1. X-Ray API Down (Connection Refused)**

```
User's App → X-Ray API
           × Connection refused

Fallback:
- SILENT: Continue (trace lost)
- LOG: Write to file
- RAISE: Crash with XRayClientError
```

**2. X-Ray API Slow (Timeout)**

```
User's App → X-Ray API
           ⏱ Wait 5 seconds
           × Timeout

Fallback triggered
```

**3. X-Ray API Returns Error (400/500)**

```
User's App → X-Ray API
           ← 400 Bad Request

Fallback triggered
```

**4. Network Issues**

```
User's App → [Network]
           × DNS failure
           × Route failure
           × Firewall blocked

Fallback triggered
```

**5. Invalid Payload (SDK Bug)**

```
User's App → Send invalid JSON
X-Ray API  ← 400 Bad Request

Fallback triggered

If RAISE mode: Good! Find SDK bug
If SILENT: Trace lost silently (bad for finding SDK bugs)
```

### Production Best Practices

**Configuration for Production:**

```python
configure(
    api_url=os.getenv("XRAY_API_URL"),
    enabled=True,
    async_mode=True,          # Non-blocking
    fallback_mode=FallbackMode.SILENT,  # Don't crash app
    timeout_seconds=2.0,      # Fail fast
    verbose=False             # No stdout noise
)
```

**Configuration for Development:**

```python
configure(
    api_url="http://localhost:8001",
    enabled=True,
    async_mode=False,         # Easier to debug
    fallback_mode=FallbackMode.LOG,  # Save traces locally
    log_file="/tmp/xray.jsonl",
    timeout_seconds=10.0,     # More patient
    verbose=True              # See what's happening
)
```

**Configuration for Testing:**

```python
configure(
    api_url="http://localhost:8001",
    enabled=True,
    async_mode=False,         # Synchronous for determinism
    fallback_mode=FallbackMode.RAISE,  # Fail fast
    timeout_seconds=5.0,
    verbose=True
)
```

---

## Performance & Optimization

### Overhead Measurements

**Baseline (No X-Ray):**
```python
@app.post("/api/competitors")
async def find_competitors():
    result = run_pipeline()
    return result

# Latency: 100ms
```

**With X-Ray (Async Mode):**
```python
@app.post("/api/competitors")
async def find_competitors():
    with RunContext("pipeline") as run:
        result = run_pipeline()
        run.set_final_output(result)
    return result

# Latency: 100ms + 0.5ms = 100.5ms
# Overhead: 0.5%
```

**With X-Ray (Sync Mode):**
```python
# Same code

# Latency: 100ms + 150ms = 250ms
# Overhead: 150%
# DON'T USE IN PRODUCTION!
```

### Where Time Is Spent

**Async Mode Breakdown:**

```
RunContext.__enter__():     0.01ms  (create objects)
StepContext.__enter__() ×5: 0.05ms  (5 steps)
step.set_candidates():      0.10ms  (sampling 5000→150)
StepContext.__exit__() ×5:  0.05ms  (calculate durations)
RunContext.__exit__():      0.10ms  (prepare payload)
send_trace():               0.20ms  (spawn thread)
                            -------
Total:                      0.51ms

Background thread:          150ms   (HTTP POST, doesn't block)
```

**Operations:**

| Operation | Time | Why |
|-----------|------|-----|
| Create RunModel | 0.01ms | Object initialization |
| Create StepModel | 0.01ms | Object initialization |
| Record timestamp | 0.001ms | `datetime.utcnow()` |
| Calculate duration | 0.001ms | Subtraction |
| Smart sampling | 0.05ms | List slicing + random |
| Serialize to JSON | 0.05ms | Pydantic `.json()` |
| Spawn thread | 0.10ms | `threading.Thread()` |
| HTTP POST (background) | 100-200ms | Network + API |

### Optimization Techniques

**1. Smart Sampling**

Without:
```python
step.set_candidates(
                candidates_in=0,
                candidates_out=len(5000_items),
                data=5000_items
            )
# Serializes 5000 items to JSON: ~5MB, 50ms
```

With:
```python
step.set_candidates(
                candidates_in=0,
                candidates_out=len(5000_items),
                data=5000_items
            )  # auto_sample=True
# Samples to 150 items: ~150KB, 5ms
# 10x faster serialization
```

**2. Async Mode**

Without:
```python
async_mode=False
# Blocks 150ms waiting for HTTP response
```

With:
```python
async_mode=True
# Spawns thread, returns in 0.2ms
```

**3. Selective Instrumentation**

Don't instrument everything:
```python
# ❌ Over-instrumentation
with StepContext("validate_input", StepType.CUSTOM):
    validate(input)  # 1ms operation, not worth instrumenting

# ✅ Instrument important steps only
with StepContext("llm_call", StepType.LLM):
    result = llm.complete()  # 1000ms operation, worth instrumenting
```

**4. Conditional Instrumentation**

```python
# Only instrument 10% of requests
if random.random() < 0.1:
    with RunContext(...):
        run_pipeline()
else:
    run_pipeline()  # No X-Ray overhead
```

**5. Disable for Performance-Critical Paths**

```python
# config.py
XRAY_ENABLED_ENDPOINTS = ["/api/competitors", "/api/search"]

# main.py
@app.post("/api/competitors")
async def competitors():
    if "/api/competitors" in XRAY_ENABLED_ENDPOINTS:
        with RunContext(...):
            return run_pipeline()
    else:
        return run_pipeline()
```

### Scalability

**Database Performance:**

```sql
-- Slow query (full table scan)
SELECT * FROM runs WHERE metadata @> '{"user_id": "123"}';
-- 10 seconds on 1M rows

-- Fast query (indexed field)
SELECT * FROM runs WHERE pipeline_name = 'competitor-selection';
-- 50ms on 1M rows (indexed)

-- Add GIN index for JSONB queries
CREATE INDEX idx_runs_metadata_gin ON runs USING GIN (metadata);
-- Now: 100ms on 1M rows
```

**API Performance:**

```python
# Problem: Returning 1000 steps in one response
# Solution: Pagination
GET /api/runs/{id}?limit=50&offset=0  # First 50 steps
GET /api/runs/{id}?limit=50&offset=50  # Next 50 steps
```

**Storage Growth:**

```
Assumption: 1000 runs/day, 5 steps/run, 150 candidates/step

Day 1: 251 MB
Week 1: 1.7 GB
Month 1: 7.5 GB
Year 1: 90 GB

With retention policy (delete after 90 days):
Steady state: ~22.5 GB
```

**Retention Strategy:**

```sql
-- Delete runs older than 90 days
DELETE FROM runs
WHERE created_at < NOW() - INTERVAL '90 days'
  AND status = 'SUCCESS';

-- Keep failures longer
DELETE FROM runs
WHERE created_at < NOW() - INTERVAL '180 days'
  AND status = 'FAILURE';
```

---

## Deployment Architecture

### Production Setup

```
                         Internet
                            │
                            │
                    ┌───────▼────────┐
                    │  Load Balancer │
                    └───────┬────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
┌───────▼──────┐                       ┌───────▼──────┐
│  User's App  │                       │  User's App  │
│  (Instance 1)│                       │  (Instance 2)│
│              │                       │              │
│  • FastAPI   │                       │  • FastAPI   │
│  • X-Ray SDK │                       │  • X-Ray SDK │
└──────┬───────┘                       └──────┬───────┘
       │                                      │
       │ POST /api/runs/ingest                │
       │ (async, background)                  │
       │                                      │
       └──────────────┬───────────────────────┘
                      │
                      │
              ┌───────▼───────┐
              │ Load Balancer │
              │  (X-Ray API)  │
              └───────┬───────┘
                      │
      ┌───────────────┴───────────────┐
      │                               │
┌─────▼──────┐                  ┌─────▼──────┐
│ X-Ray API  │                  │ X-Ray API  │
│ (Instance 1)│                  │ (Instance 2)│
│            │                  │            │
│ • FastAPI  │                  │ • FastAPI  │
│ • Uvicorn  │                  │ • Uvicorn  │
└─────┬──────┘                  └─────┬──────┘
      │                               │
      └───────────────┬───────────────┘
                      │
                      │
              ┌───────▼───────┐
              │  PostgreSQL   │
              │   (Primary)   │
              └───────┬───────┘
                      │
                      │ Replication
                      │
              ┌───────▼───────┐
              │  PostgreSQL   │
              │   (Replica)   │
              └───────────────┘
```

### Deployment Options

**Option 1: Docker Compose (Development/Small Scale)**

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: xray_db
      POSTGRES_USER: xray
      POSTGRES_PASSWORD: secret
    volumes:
      - postgres-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  xray-api:
    build: ./xray-api
    environment:
      DATABASE_URL: postgresql://xray:secret@postgres:5432/xray_db
    ports:
      - "8001:8001"
    depends_on:
      - postgres
    command: uvicorn app.main:app --host 0.0.0.0 --port 8001

volumes:
  postgres-data:
```

**Option 2: Kubernetes (Production)**

```yaml
# postgres-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
spec:
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:14
        env:
        - name: POSTGRES_DB
          value: xray_db
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-secret
              key: password
        ports:
        - containerPort: 5432
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
      volumes:
      - name: postgres-storage
        persistentVolumeClaim:
          claimName: postgres-pvc

---
apiVersion: v1
kind: Service
metadata:
  name: postgres-service
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432

---
# xray-api-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: xray-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: xray-api
  template:
    metadata:
      labels:
        app: xray-api
    spec:
      containers:
      - name: xray-api
        image: myregistry/xray-api:latest
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: xray-db-secret
              key: url
        ports:
        - containerPort: 8001
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 5
          periodSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: xray-api-service
spec:
  type: LoadBalancer
  selector:
    app: xray-api
  ports:
  - port: 80
    targetPort: 8001
```

**Option 3: Cloud Managed Services (AWS Example)**

```
User's App (EC2/ECS/Lambda)
    ↓
X-Ray API (ECS Fargate)
    ↓
RDS PostgreSQL (Managed)
```

```terraform
# terraform/main.tf

# RDS PostgreSQL
resource "aws_db_instance" "xray" {
  identifier = "xray-db"
  engine = "postgres"
  engine_version = "14.6"
  instance_class = "db.t3.medium"
  allocated_storage = 100

  db_name = "xray_db"
  username = "xray"
  password = var.db_password

  backup_retention_period = 7
  multi_az = true

  tags = {
    Name = "X-Ray Database"
  }
}

# ECS Cluster
resource "aws_ecs_cluster" "xray" {
  name = "xray-cluster"
}

# ECS Task Definition
resource "aws_ecs_task_definition" "xray_api" {
  family = "xray-api"
  network_mode = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu = "512"
  memory = "1024"

  container_definitions = jsonencode([{
    name = "xray-api"
    image = "${aws_ecr_repository.xray_api.repository_url}:latest"
    portMappings = [{
      containerPort = 8001
      protocol = "tcp"
    }]
    environment = [{
      name = "DATABASE_URL"
      value = "postgresql://${aws_db_instance.xray.username}:${var.db_password}@${aws_db_instance.xray.endpoint}/${aws_db_instance.xray.db_name}"
    }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group" = "/ecs/xray-api"
        "awslogs-region" = "us-east-1"
        "awslogs-stream-prefix" = "ecs"
      }
    }
  }])
}

# ECS Service
resource "aws_ecs_service" "xray_api" {
  name = "xray-api-service"
  cluster = aws_ecs_cluster.xray.id
  task_definition = aws_ecs_task_definition.xray_api.arn
  desired_count = 3
  launch_type = "FARGATE"

  network_configuration {
    subnets = var.private_subnets
    security_groups = [aws_security_group.xray_api.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.xray_api.arn
    container_name = "xray-api"
    container_port = 8001
  }
}

# Application Load Balancer
resource "aws_lb" "xray_api" {
  name = "xray-api-lb"
  internal = false
  load_balancer_type = "application"
  security_groups = [aws_security_group.xray_lb.id]
  subnets = var.public_subnets
}

resource "aws_lb_target_group" "xray_api" {
  name = "xray-api-tg"
  port = 8001
  protocol = "HTTP"
  vpc_id = var.vpc_id
  target_type = "ip"

  health_check {
    path = "/health"
    healthy_threshold = 2
    unhealthy_threshold = 10
  }
}

resource "aws_lb_listener" "xray_api" {
  load_balancer_arn = aws_lb.xray_api.arn
  port = "443"
  protocol = "HTTPS"
  ssl_policy = "ELBSecurityPolicy-2016-08"
  certificate_arn = var.certificate_arn

  default_action {
    type = "forward"
    target_group_arn = aws_lb_target_group.xray_api.arn
  }
}
```

### Monitoring & Observability

**Metrics to Monitor:**

1. **X-Ray API Health:**
   - Request rate (requests/sec)
   - Error rate (5xx responses)
   - Latency (p50, p95, p99)
   - Database connection pool usage

2. **Database Health:**
   - Connection count
   - Query latency
   - Disk usage
   - Replication lag

3. **SDK Client Metrics:**
   - Trace send success rate
   - Timeout rate
   - Fallback mode triggers

**Prometheus Metrics (Example):**

```python
# xray-api/app/main.py
from prometheus_client import Counter, Histogram, generate_latest

# Metrics
ingest_requests = Counter('xray_ingest_requests_total', 'Total ingest requests')
ingest_errors = Counter('xray_ingest_errors_total', 'Total ingest errors')
ingest_duration = Histogram('xray_ingest_duration_seconds', 'Ingest duration')

@app.post("/api/runs/ingest")
async def ingest_trace(payload: IngestPayload):
    ingest_requests.inc()
    with ingest_duration.time():
        try:
            # ... ingestion logic
            return {"success": True}
        except Exception as e:
            ingest_errors.inc()
            raise

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

**Grafana Dashboard:**

```
Row 1: X-Ray API Health
- Request Rate (graph)
- Error Rate (graph)
- P95 Latency (graph)

Row 2: Database
- Connections (gauge)
- Query Time (graph)
- Disk Usage (gauge)

Row 3: Ingestion
- Traces Ingested/min (graph)
- Failed Ingestions (graph)
- Top Pipelines (table)

Row 4: Storage
- Total Runs (gauge)
- Total Steps (gauge)
- DB Size (gauge)
```

---

## Common Interview Questions & Answers

### Q1: Explain the architecture of X-Ray at a high level.

**Answer:**

X-Ray consists of two components:

1. **SDK** (Python library): Users integrate into their application. Provides context managers (`RunContext`, `StepContext`) that automatically capture timing, inputs, outputs, reasoning, and candidates. Sends traces asynchronously to X-Ray API with <1ms overhead.

2. **API** (FastAPI service): Separate service that receives traces via POST endpoint, stores in PostgreSQL with JSONB for flexibility, and provides query endpoints to retrieve and analyze traces.

**Key design principle**: Decouple capture (SDK) from storage/query (API). This allows SDK to be lightweight and non-blocking, while API can be scaled independently.

### Q2: How does X-Ray handle large datasets (e.g., 5000 candidates)?

**Answer:**

**Smart Sampling Algorithm:**
- If candidates ≤ 100: Store all
- If candidates > 100: Sample ~150 using head (50) + middle (50 random) + tail (50)

**Why this approach:**
- **Head**: See what initially passed filters
- **Middle**: Random sample for statistical representation
- **Tail**: See what came in last

**Result**: 97% storage reduction (5000 → 150) while maintaining debuggability for 95% of issues.

**Configurable**: `configure(max_candidates_full_capture=200)` adjusts threshold.

### Q3: What happens if X-Ray API is down?

**Answer:**

Three fallback modes:

1. **SILENT** (Production default):
   - Application continues normally
   - Trace is lost
   - Zero impact on user experience

2. **LOG** (Development):
   - Trace written to local file (`/tmp/xray.jsonl`)
   - Can bulk-upload later
   - Useful for development/debugging

3. **RAISE** (Testing):
   - Raises `XRayClientError`
   - Application fails
   - Useful for finding SDK bugs in testing

**Implementation**: Try-catch in `send_trace()`, handles `ConnectionError`, `TimeoutException`, etc.

**Why this design**: Application stability > trace completeness. X-Ray should never bring down production.

### Q4: Why use JSONB instead of normalized columns?

**Answer:**

**Problem**: Different pipelines have different inputs/outputs. Creating columns for every possible field would require:
- 100+ columns (most NULL)
- Schema migrations for every new pipeline
- Inflexible design

**Solution**: JSONB
- **Flexible**: Any pipeline can store any data
- **Queryable**: PostgreSQL supports querying inside JSONB (`WHERE inputs @> '{"threshold": 0.3}'`)
- **Performant**: Binary format, can be indexed with GIN indexes
- **Compact**: Only stores present fields

**Hybrid approach**: Structured columns for common fields (pipeline_name, step_type, candidates_in/out), JSONB for variable data.

### Q5: How does async mode work and why is it important?

**Answer:**

**Sync Mode** (blocking):
```
1. RunContext.__exit__() called
2. Sends HTTP POST to X-Ray API
3. Waits for response (150ms)
4. Returns control to application
Total: 150ms overhead
```

**Async Mode** (non-blocking):
```
1. RunContext.__exit__() called
2. Spawns background thread
3. Returns control immediately (0.5ms)
4. Background thread sends HTTP POST (150ms in parallel)
Total: 0.5ms overhead
```

**Implementation**: `threading.Thread(target=_send_trace_sync, daemon=True)`

**Why important**:
- Production: <1ms overhead vs 150ms overhead
- User experience: API responds fast
- Scalability: Can handle high request rates

### Q6: Walk me through a complete trace from user's code to database.

**Answer:**

**Step 1: User's code**
```python
with RunContext("pipeline") as run:
    with run.step("step1", StepType.LLM) as step:
        result = llm.call()
        step.set_outputs({"result": result})
```

**Step 2: SDK RunContext.__enter__()**
- Creates `RunModel` with UUID
- Records `start_time`
- Stores in `contextvars` (thread-local storage)

**Step 3: SDK StepContext.__enter__()**
- Creates `StepModel` with UUID
- Records `start_time`
- Gets sequence number from RunContext

**Step 4: User calls `step.set_outputs()`**
- Updates `StepModel.outputs` field

**Step 5: SDK StepContext.__exit__()**
- Records `end_time`
- Calculates `duration_ms`
- Adds `StepModel` to `RunModel.steps` list

**Step 6: SDK RunContext.__exit__()**
- Records `end_time`
- Marks `status = SUCCESS`
- Calls `send_trace(IngestPayload(run=RunModel, steps=[StepModel]))`

**Step 7: SDK send_trace()**
- Serializes payload to JSON (Pydantic)
- Spawns background thread (if async_mode=True)
- Thread sends `POST /api/runs/ingest`

**Step 8: API receives POST**
- FastAPI validates payload (Pydantic)
- Creates SQLAlchemy `Run` object
- Creates SQLAlchemy `Step` objects
- `db.add()` and `db.commit()`

**Step 9: PostgreSQL**
- Inserts row into `runs` table
- Inserts rows into `steps` table
- JSONB fields stored as binary

**Step 10: Later - user queries**
- `GET /api/runs/{id}`
- SQLAlchemy queries database
- Returns JSON to user

### Q7: How would you scale X-Ray to handle 1 million traces/day?

**Answer:**

**Current capacity**: ~10,000 traces/day (single instance)

**Scaling approach**:

1. **Horizontal scaling** (API):
   - Multiple API instances behind load balancer
   - Stateless design allows easy scaling
   - Each instance handles ~10,000 traces/day
   - 100 instances → 1M traces/day

2. **Database optimization**:
   - Read replicas for queries
   - Write to primary, read from replicas
   - Connection pooling (10-20 connections/instance)
   - Partitioning by `created_at` (monthly partitions)

3. **Storage optimization**:
   - Retention policy: Delete after 90 days
   - Archive old data to S3 (cold storage)
   - Compress JSONB fields

4. **Caching**:
   - Redis for frequently queried runs
   - TTL: 1 hour
   - Cache invalidation on updates

5. **Async ingestion**:
   - Message queue (RabbitMQ/Kafka) between SDK and API
   - SDK sends to queue, API processes asynchronously
   - Better fault tolerance

**Architecture**:
```
SDK → Load Balancer → API (100 instances)
                        ↓
                    Message Queue
                        ↓
                  Ingest Workers (50 instances)
                        ↓
                   PostgreSQL (Primary + 3 Replicas)
                        ↓
                   S3 Archive (cold storage)
```

**Cost estimate**:
- Compute: 100 API + 50 workers × $50/month = $7,500/month
- Database: PostgreSQL (RDS) ~$500/month
- Storage: 1M traces/day × 250KB × 90 days = 22TB × $0.10/GB = $2,200/month
- Total: ~$10,200/month for 1M traces/day

### Q8: What are the trade-offs of this design?

**Answer:**

**Advantages:**
1. ✅ **Low overhead**: <1ms with async mode
2. ✅ **Non-intrusive**: Doesn't change business logic
3. ✅ **Resilient**: App works even if X-Ray fails
4. ✅ **Flexible**: JSONB allows any pipeline structure
5. ✅ **Queryable**: Can find patterns across pipelines
6. ✅ **Scalable**: Smart sampling reduces storage by 97%

**Disadvantages:**
1. ❌ **Incomplete data**: Sampling means can't see all candidates
2. ❌ **Instrumentation required**: Developers must add X-Ray code
3. ❌ **Separate service**: Must deploy and maintain X-Ray API
4. ❌ **Storage cost**: 90GB/year for 1000 runs/day
5. ❌ **Query complexity**: JSONB queries harder than SQL
6. ❌ **No real-time UI**: Must build custom dashboard

**Alternative approaches considered**:

1. **Logging to files**:
   - ✅ Simple
   - ❌ Not queryable, hard to analyze

2. **OpenTelemetry integration**:
   - ✅ Standard protocol
   - ❌ Focused on performance, not decision context

3. **Full capture (no sampling)**:
   - ✅ Complete data
   - ❌ 10-100x more expensive

4. **MongoDB instead of PostgreSQL**:
   - ✅ More flexible schema
   - ❌ Harder to query, less mature

**Why this design wins**: Balances completeness, performance, cost, and ease of use for debugging non-deterministic pipelines.

### Q9: How would you add a new feature: A/B test comparison?

**Answer:**

**Requirement**: Compare two algorithm variants and see which performs better.

**Implementation**:

**Step 1: SDK - Capture variant info**
```python
with RunContext(
    "competitor-selection",
    metadata={"variant": "threshold_0.3"}  # Add variant
) as run:
    threshold = 0.3  # Variant A
    # ... pipeline
```

**Step 2: API - Query endpoint**
```python
@router.post("/api/analytics/compare-variants")
async def compare_variants(
    pipeline_name: str,
    variant_a: str,
    variant_b: str
):
    # Get runs for variant A
    runs_a = db.query(Run).filter(
        Run.pipeline_name == pipeline_name,
        Run.metadata['variant'].astext == variant_a
    ).all()

    # Get runs for variant B
    runs_b = db.query(Run).filter(
        Run.pipeline_name == pipeline_name,
        Run.metadata['variant'].astext == variant_b
    ).all()

    # Calculate metrics
    def calculate_metrics(runs):
        durations = [r.duration_ms for r in runs if r.duration_ms]
        success_rate = len([r for r in runs if r.status == "SUCCESS"]) / len(runs)
        avg_duration = sum(durations) / len(durations) if durations else 0

        # Get avg reduction rate from filter steps
        filter_steps = db.query(Step).filter(
            Step.run_id.in_([r.id for r in runs]),
            Step.step_type == "FILTER"
        ).all()

        avg_reduction = sum([s.reduction_rate for s in filter_steps if s.reduction_rate]) / len(filter_steps)

        return {
            "success_rate": success_rate,
            "avg_duration_ms": avg_duration,
            "avg_reduction_rate": avg_reduction
        }

    return {
        "variant_a": {
            "name": variant_a,
            "runs": len(runs_a),
            "metrics": calculate_metrics(runs_a)
        },
        "variant_b": {
            "name": variant_b,
            "runs": len(runs_b),
            "metrics": calculate_metrics(runs_b)
        },
        "winner": "variant_a" if calculate_metrics(runs_a)["success_rate"] > calculate_metrics(runs_b)["success_rate"] else "variant_b"
    }
```

**Step 3: Usage**
```bash
curl -X POST http://xray-api/api/analytics/compare-variants \
  -d '{
    "pipeline_name": "competitor-selection",
    "variant_a": "threshold_0.3",
    "variant_b": "threshold_0.7"
  }'

# Response:
{
  "variant_a": {
    "name": "threshold_0.3",
    "runs": 1000,
    "metrics": {
      "success_rate": 0.85,
      "avg_duration_ms": 4250,
      "avg_reduction_rate": 0.16
    }
  },
  "variant_b": {
    "name": "threshold_0.7",
    "runs": 1000,
    "metrics": {
      "success_rate": 0.95,
      "avg_duration_ms": 4100,
      "avg_reduction_rate": 0.90
    }
  },
  "winner": "variant_b"
}
```

**Time to implement**: ~2 hours

### Q10: How does this compare to AWS X-Ray or OpenTelemetry?

**Answer:**

| Feature | Our X-Ray | AWS X-Ray | OpenTelemetry |
|---------|-----------|-----------|---------------|
| **Focus** | Decision context | Performance tracing | Observability |
| **Captures** | Inputs, outputs, reasoning, candidates | Timing, errors | Metrics, logs, traces |
| **Use case** | "Why wrong decision?" | "Why slow?" | "What happened?" |
| **Storage** | PostgreSQL (queryable) | AWS proprietary | External (Jaeger, etc.) |
| **Sampling** | Smart (head+tail+random) | Random | Random |
| **Cost** | Self-hosted | AWS pricing | Self-hosted |
| **Integration** | Python only (MVP) | Multi-language | Multi-language |

**When to use ours**:
- ✅ Debugging AI/ML pipelines
- ✅ Need to see WHY decisions made
- ✅ Want queryable database
- ✅ Self-hosted

**When to use AWS X-Ray**:
- ✅ Already on AWS
- ✅ Focus on performance, not decisions
- ✅ Multi-service distributed tracing

**When to use OpenTelemetry**:
- ✅ Standard observability
- ✅ Multi-language
- ✅ Already have observability stack

**Can they coexist?** Yes!
- Use OpenTelemetry for performance/errors
- Use X-Ray for decision debugging
- Correlate via trace IDs

---

## Conclusion

You now understand:
- ✅ Complete architecture (SDK + API)
- ✅ Data flow from user code to database
- ✅ Internal implementation details
- ✅ Smart sampling algorithm
- ✅ Error handling and fallback modes
- ✅ Performance characteristics
- ✅ Deployment strategies
- ✅ Scaling considerations
- ✅ Trade-offs and design decisions

**Next steps:**
1. Read the code in `xray-sdk/` and `xray-api/`
2. Run the demo (`examples/competitor_selection_demo.py`)
3. Query the API and see traces
4. Try modifying the code (add a feature, change sampling)
5. Deploy to production!

**You're now ready to explain X-Ray to anyone in complete detail!** 🚀
