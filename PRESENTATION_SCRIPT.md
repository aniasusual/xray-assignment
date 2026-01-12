# X-Ray Project - 7 Minute Explanation Script

**Total time: ~7-8 minutes**

---

## 1. THE PROBLEM (1 minute)

"Let me explain the problem X-Ray solves.

Imagine you have an e-commerce website. A customer searches for an iPhone case, but your system recommends a laptop stand. That's wrong!

Traditional logging tells you WHAT happened - the function ran, it took 120 milliseconds. But it doesn't tell you WHY the wrong product was selected.

You have to:
- Add print statements
- Redeploy code
- Wait for the bug to happen again
- Look at logs
- Still don't understand why

This takes hours or days to debug.

X-Ray solves this. It captures WHY decisions were made, so you can debug in minutes instead of hours."

---

## 2. THE SOLUTION (1 minute)

"X-Ray has two parts:

**Part 1 - The SDK**: A Python library that developers add to their code. It's like a flight recorder - it captures everything that happens.

**Part 2 - The API**: A separate service that stores all the data and lets you query it later.

Here's how it works:
- Your application runs normally
- X-Ray SDK captures data in the background (takes less than 1 millisecond)
- Data is sent to X-Ray API
- When a bug happens, you query the API to see exactly what went wrong

No terminal output, no print statements. You query when you need to debug."

---

## 3. HOW USERS INTEGRATE IT (1.5 minutes)

"Let me show you how a developer uses X-Ray.

**Step 1 - Configure once at startup:**

```python
from xray import configure

configure(
    api_url='http://xray-api.mycompany.com',
    enabled=True,
    async_mode=True
)
```

This tells X-Ray where to send data.

**Step 2 - Wrap your pipeline:**

```python
with RunContext('competitor-selection') as run:
    # Your existing code
    product = get_product(product_id)
    candidates = search_catalog(product)
    filtered = filter_by_category(candidates)
    result = rank_by_relevance(filtered)
    return result
```

**Step 3 - Wrap important steps:**

```python
with RunContext('competitor-selection') as run:

    with StepContext('search', StepType.SEARCH) as step:
        candidates = search_catalog(product)
        step.set_candidates(candidates)

    with StepContext('filter', StepType.FILTER) as step:
        filtered = filter_by_category(candidates, threshold=0.3)
        step.set_candidates(filtered, previous_count=len(candidates))
        step.set_reasoning('Filtered using threshold 0.3')

    with StepContext('rank', StepType.RANK) as step:
        result = rank_by_relevance(filtered)
        step.set_candidates(result)

    return result
```

That's it! Your application now sends traces to X-Ray automatically."

---

## 4. HOW IT WORKS INTERNALLY (1.5 minutes)

"Now let me explain what happens inside.

**When you use 'with RunContext':**
- Python calls `__enter__()` method
- X-Ray records the start time
- X-Ray stores this in something called 'context variables' - think of it like a thread-safe global variable

**When you use 'with StepContext':**
- Python calls `__enter__()` method
- X-Ray looks up the parent RunContext from context variables
- Records start time for this step

**When your code finishes:**
- Python calls `__exit__()` method
- X-Ray records end time
- Calculates duration (end time minus start time)
- For RunContext: sends all data to X-Ray API in background thread
- Your application continues immediately - no waiting!

**Key feature - Smart Sampling:**
If you have 5000 candidates, X-Ray doesn't store all 5000. It samples:
- First 50 items
- Last 50 items
- Random 50 from middle

Total: 150 items instead of 5000. That's 97% less storage!

Why this works: You can still see patterns and debug most issues."

---

## 5. DEBUGGING WITH X-RAY (1.5 minutes)

"Now the important part - how do you actually debug?

**Scenario:** Customer reports laptop stand was returned for iPhone case search.

**Step 1 - Query X-Ray API:**

```bash
curl 'http://xray-api/api/runs?pipeline_name=competitor-selection'
```

This shows all recent runs of that pipeline.

**Step 2 - Get details:**

```bash
curl 'http://xray-api/api/runs/{run_id}'
```

**Step 3 - Analyze the response:**

```json
{
  "steps": [
    {
      "step_name": "filter",
      "reasoning": "Filtered using threshold 0.3",
      "candidates_in": 5000,
      "candidates_out": 4200,
      "duration_ms": 120
    }
  ]
}
```

**What you see:**
- Threshold was 0.3 (too low!)
- Only filtered 16% of candidates (should filter 70-90%)
- That's why laptop stand got through

**Root cause found in 2 minutes!**

**The fix:**
Change threshold from 0.3 to 0.7. Deploy. Done."

---

## 6. KEY TECHNICAL CONCEPTS (1 minute)

"Let me explain three important technical concepts:

**1. Context Managers (the 'with' statement):**
- Python feature that ensures cleanup happens
- `__enter__()` runs when entering the block
- `__exit__()` runs when exiting the block
- X-Ray uses this to automatically capture start time and end time

**2. Context Variables:**
- Thread-safe storage
- Each thread has its own copy
- StepContext uses this to find its parent RunContext
- No need to pass RunContext around manually

**3. Async Mode:**
- Sends data in background thread
- Your application doesn't wait
- Overhead is less than 1 millisecond
- If X-Ray API is down, your app still works"

---

## 7. DATABASE & STORAGE (45 seconds)

"X-Ray stores data in PostgreSQL.

**Two tables:**

**Runs table:**
- Stores one row per pipeline execution
- Fields: pipeline name, start time, end time, status, metadata

**Steps table:**
- Stores one row per step
- Fields: step name, step type, duration, inputs, outputs, reasoning, candidates

**Why JSONB:**
Different pipelines have different inputs and outputs. We can't create columns for every possibility. JSONB lets us store any structure flexibly.

**Storage:** With smart sampling, 1000 runs per day = about 250MB per day."

---

## 8. REAL WORLD VALUE (30 seconds)

"Why is X-Ray valuable?

**Traditional debugging:**
- Add logs, redeploy, reproduce bug, analyze
- Takes hours or days
- Disrupts production

**With X-Ray:**
- Data already captured
- Query API, see exact trace
- Find root cause in minutes
- No code changes needed

**Example results:**
- Bug that would take 4 hours → Fixed in 10 minutes
- 97% storage savings from smart sampling
- Less than 1ms overhead on your application
- Works even if X-Ray API goes down"

---

## 9. CLOSING (30 seconds)

"To summarize:

**X-Ray is a debugging system for AI pipelines.**

It captures:
- What happened (timing, data flow)
- WHY it happened (reasoning, parameters, decisions)

Two components:
- SDK: Lightweight library in your code
- API: Separate service for storage and queries

Result:
- Debug in minutes instead of hours
- No production disruptions
- Complete visibility into decision-making

That's X-Ray. Questions?"

---

## TIMING BREAKDOWN

1. Problem: 1 min
2. Solution: 1 min
3. Integration: 1.5 min
4. Internal workings: 1.5 min
5. Debugging flow: 1.5 min
6. Technical concepts: 1 min
7. Database: 45 sec
8. Value: 30 sec
9. Closing: 30 sec

**Total: ~8 minutes**

---

## TIPS FOR DELIVERY

- **Speak slowly and clearly**
- **Pause between sections** (2-3 seconds)
- **Show code examples on screen** if possible
- **Use hand gestures** when explaining "background thread" or "two components"
- **Make eye contact**
- **Emphasize key numbers**: "97% storage savings", "less than 1 millisecond"
- **Be ready for questions** after each section

## POSSIBLE QUESTIONS & ANSWERS

**Q: What if X-Ray API is down?**
A: Your app keeps working. We have fallback modes - either ignore silently, or save traces to a local file.

**Q: What's the performance impact?**
A: Less than 1 millisecond overhead with async mode. We measured it.

**Q: How much does it cost to store data?**
A: With smart sampling, about 250MB per day for 1000 pipeline runs. That's roughly $7-10 per month in cloud storage.

**Q: Can it work with languages other than Python?**
A: Currently Python only, but the API is language-agnostic. Could build SDKs for JavaScript, Go, Java, etc.

**Q: How is this different from traditional logging?**
A: Logs tell you WHAT happened. X-Ray tells you WHY. It captures decision context, not just events.
