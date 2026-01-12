# X-Ray Project - 10 Minute Video Script

**Total time: 9-10 minutes max**

---

## VIDEO SETUP (Before Recording)

- **Camera on**: Ensure your face is visible throughout
- **Screen share ready**: Have terminal, code editor, browser open
- **Demo ready**: API running, demo script ready to execute
- **Relaxed tone**: Talk like explaining to a colleague, not reading a doc

---

## 1. INTRODUCTION (30 seconds)

"Hi, I'm [Your Name]. I built X-Ray, a debugging system for non-deterministic pipelines.

The problem is simple: when an AI-powered pipeline returns the wrong result—like matching a phone case to a laptop stand—traditional logging tells you WHAT happened, but not WHY.

X-Ray solves this by capturing decision context at each step: inputs, outputs, reasoning, and candidates.

Let me walk you through the architecture, show it working, and share a challenge I faced while building it."

---

## 2. ARCHITECTURE OVERVIEW (2.5 minutes)

### Two Components

"X-Ray has two parts:

**The SDK** (Python library):
- Developers wrap their pipeline with context managers
- Captures timing, inputs, outputs, reasoning automatically
- Sends data to API asynchronously (<1ms overhead)

**The API** (FastAPI + PostgreSQL):
- Stores traces in two tables: Runs and Steps
- Provides query endpoints for debugging"

### Data Model Design Decisions

*[Show ARCHITECTURE.md diagram or draw on screen]*

"Let me explain key design decisions:

**Decision 1: Two tables, not embedded documents**

Why? Because I need queries like 'show all FILTER steps with >90% reduction' across different pipelines. With PostgreSQL + indexes, this is O(log n). With MongoDB embedded, I'd scan every document.

Alternative I considered: Embedded steps in MongoDB. Rejected because cross-pipeline analytics become impossible.

**Decision 2: JSONB for variable data**

Each pipeline has different fields. Competitor selection stores 'keywords', categorization stores 'confidence_scores'. JSONB lets me handle this without migrations.

Alternative: Strict schema with columns. But adding a new pipeline type would require database migration every time.

**Decision 3: Standardized step types**

I enforce an enum: LLM, SEARCH, FILTER, RANK, SELECT. This enables cross-pipeline queries.

Without it, developers would use 'filter', 'filtering', 'prune'—fragmenting the data and breaking analytics.

**Decision 4: Smart sampling**

The big challenge: a step with 5000 candidates = 5MB. 10 steps = 50MB/run. 1000 runs/day = 50GB/day.

My solution: Sample 150 candidates (head 50 + tail 50 + random 50). This gives 97% storage reduction while preserving debuggability for 95% of issues.

Trade-off: You lose full visibility, but sampling captures patterns. Developers can override for critical data."

---

## 3. LIVE DEMO (2.5 minutes)

*[Switch to terminal/browser]*

"Let me show you how this works in practice.

**Step 1: Start the API**

*[Show terminal with API running]*

```bash
cd xray-api
uvicorn app.main:app --port 8001
```

API is running on port 8001.

**Step 2: Run the demo pipeline**

*[Show code in editor briefly]*

This is a competitor selection pipeline with a deliberate bug—the filter threshold is too low (0.3).

*[Run demo]*

```bash
cd xray-sdk/examples
python3 competitor_selection_demo.py
```

*[Point to output]*

It selected a laptop stand for an iPhone case—wrong match. But X-Ray captured the trace.

**Step 3: Debug using X-Ray API**

*[Show browser or curl commands]*

First, list all runs:

```bash
curl http://127.0.0.1:8001/api/runs
```

*[Show JSON response briefly]*

Found the run. Now get details:

```bash
curl http://127.0.0.1:8001/api/runs/{run_id}
```

*[Scroll to filter step in JSON]*

Look at the filter step:
- Candidates in: 5000
- Candidates out: 4200
- **Only 16% filtered!** Should be 90%.
- Filter threshold: 0.3 ← **Too low**

That's why the laptop stand got through.

*[Show rank step]*

And here, the ranking step gave the laptop stand a score of 0.89 because of a price match boost.

**Root cause found in 2 minutes.**

The fix: Change threshold from 0.3 to 0.7. That's it."

---

## 4. REFLECTION: A CHALLENGE I FACED (2 minutes)

"Let me share a moment where I was stuck.

**The Challenge**: How to handle cross-pipeline queries.

Initially, I thought: 'Just let developers store whatever data they want in JSONB—total flexibility.'

But then I realized: if everyone stores data differently, how do you query 'all FILTER steps with high reduction rates' across pipelines?

**My solution came in two parts**:

**Part 1: Standardize step types**

I created an enum: LLM, SEARCH, FILTER, RANK, SELECT. This gives structure while allowing variability within each type.

**Part 2: Naming conventions**

I enforce `verb_noun` patterns like `filter_by_price`, `rank_by_relevance`. This makes it clear what each step does.

**The trade-off**: I'm constraining developers. They can't just use any step name. But this constraint enables powerful cross-pipeline analytics.

**Why this matters**: You can now ask questions like 'show me all filtering steps that eliminated >90% of candidates' across competitor-selection, fraud-detection, categorization—completely different domains.

This tension between flexibility and queryability was the hardest design decision. I chose queryability because debugging value depends on it."

---

## 5. TECHNICAL DEPTH: DEVELOPER EXPERIENCE (1.5 minutes)

"Let me quickly cover developer experience.

**Minimal integration** (3 lines):
```python
with RunContext("my-pipeline") as run:
    # existing code
    run.set_final_output(result)
```

You get run timing and final output. No per-step visibility.

**Full integration** (~5 lines per step):
```python
with run.step("filter", StepType.FILTER) as step:
    step.set_inputs({"threshold": 0.7})
    filtered = filter_func(candidates)
    step.set_candidates(
        candidates_in=len(candidates),
        candidates_out=len(filtered),
        data=filtered
    )
    step.set_reasoning("Filtered by threshold")
```

You get complete visibility: timing, inputs, outputs, reasoning, candidates.

**Fallback modes**:
- If X-Ray API is down, your pipeline keeps running
- Production: Silent mode (no errors)
- Development: Log to file, upload later

This was important—X-Ray should never break production pipelines."

---

## 6. REAL-WORLD VALUE (1 minute)

"Why does this matter?

I worked on an e-commerce search system where 'wireless headphones' returned corded headphones in top 10.

**Without X-Ray**: 3-4 days debugging. We had Elasticsearch logs, Datadog APM for timing, but couldn't see which of 6 stages failed.

**With X-Ray**: We would've found in 10 minutes that the query parser extracted 'connectivity: wireless' but the filter step didn't apply it.

This pattern repeats: competitor selection, listing optimization, fraud detection—any multi-step, non-deterministic pipeline.

**Key insight**: Traditional tracing tells you WHAT functions ran. X-Ray tells you WHY decisions were made."

---

## 7. CLOSING (30 seconds)

"To summarize:

**X-Ray = debugging system for AI pipelines**

Architecture:
- Two tables (Runs + Steps) for queryability
- JSONB for flexibility, standardized types for analytics
- Smart sampling (97% storage reduction)

Result:
- Debug in minutes vs hours/days
- Works across different pipeline types
- <1ms overhead, doesn't break production

That's X-Ray. Happy to answer questions!"

---

## TIMING BREAKDOWN

1. Introduction: 30 sec
2. Architecture: 2.5 min
3. Live Demo: 2.5 min
4. Reflection (Challenge): 2 min
5. Developer Experience: 1.5 min
6. Real-World Value: 1 min
7. Closing: 30 sec

**Total: ~10 minutes**

---

## DELIVERY TIPS

### Before Recording
- [ ] API running on port 8001
- [ ] Terminal ready with commands in history (use ↑ arrow)
- [ ] Browser tab open to localhost:8001/docs
- [ ] Code editor showing key files
- [ ] Camera positioned, face visible
- [ ] Good lighting, quiet room

### During Recording
- **Speak to the camera** like explaining to a colleague
- **Don't read the document** - explain in your own words
- **Show, don't tell** - point at code, JSON responses, terminal output
- **Pause between sections** (2-3 seconds)
- **Emphasize key numbers**: "97% storage reduction", "10 minutes vs 3 days"
- **Use hand gestures** when explaining concepts
- **Make eye contact** with camera

### What to Show on Screen
- **Architecture section**: ARCHITECTURE.md or draw diagram
- **Demo section**: Terminal + browser + code editor
- **Reflection section**: Your face (camera) + possibly code/architecture
- **Closing**: Your face (camera)

---

## POSSIBLE QUESTIONS (If Interviewer Asks)

**Q: What if X-Ray API is down?**
A: Pipeline keeps running. Fallback modes: SILENT (production), LOG (development), RAISE (testing).

**Q: Performance impact?**
A: <1ms overhead with async mode. Background thread sends data, pipeline doesn't wait.

**Q: How much storage?**
A: With smart sampling, ~250MB/day for 1000 runs. About $7-10/month in cloud storage.

**Q: Why not use existing tracing tools (Jaeger, Zipkin)?**
A: They answer "what functions ran and how long?" X-Ray answers "why did the system make this decision?" Different problem.

**Q: What's the hardest part to get right?**
A: Balancing flexibility (any pipeline type) vs queryability (cross-pipeline analytics). My solution: standardized step types + JSONB for variable data.

**Q: Would you change anything?**
A: If rebuilding, I'd add a "diff viewer" to compare two runs side-by-side for A/B testing. Would've helped with the e-commerce search debugging.

---

## SCREEN FLOW

```
[Your face] → Introduction
[Screen: Architecture doc/diagram] → Architecture explanation
[Screen: Terminal + Browser] → Live demo
[Your face] → Reflection on challenge
[Screen: Code editor] → Developer experience
[Your face] → Real-world value + Closing
```

---

## DEMO COMMANDS (Copy-paste ready)

```bash
# Terminal 1: Start API
cd xray-api
source .venv/bin/activate
uvicorn app.main:app --reload --port 8001

# Terminal 2: Run demo
cd xray-sdk/examples
source ../.venv/bin/activate
python3 competitor_selection_demo.py

# Terminal 3: Query API
curl http://127.0.0.1:8001/api/runs
curl http://127.0.0.1:8001/api/runs/{run_id}

# Or use browser
open http://127.0.0.1:8001/docs
```

---

## FINAL CHECKLIST

Before submitting video:
- [ ] Total time ≤ 10 minutes
- [ ] Face visible throughout
- [ ] Architecture explained (not read)
- [ ] Live demo shown
- [ ] Challenge/reflection included
- [ ] Clear audio, no background noise
- [ ] Video uploaded (YouTube unlisted)
- [ ] Link added to submission form
