#!/usr/bin/env python3
"""
Competitor Selection Pipeline Demo

This demonstrates a realistic e-commerce competitor selection pipeline that:
1. Generates search keywords from a product title (LLM step)
2. Searches product catalog (Search step)
3. Filters by category similarity (Filter step)
4. Ranks by relevance (Rank step)
5. Selects the best competitor (Select step)

This demo includes a deliberate bug (low category similarity threshold)
that causes incorrect matches - demonstrating how X-Ray helps debug.
"""

import random
import time
from typing import List, Dict, Any
from datetime import datetime

from xray import RunContext, StepType, configure

# Configure X-Ray
configure(
    api_url="http://127.0.0.1:8001",
    enabled=True,
    async_mode=True,
    verbose=True
)


# ============================================================================
# Mock Data - Simulating a product catalog
# ============================================================================

PRODUCT_CATALOG = [
    # iPhone Cases (correct category)
    {"asin": "B09ABC001", "title": "iPhone 15 Pro Clear Case", "category": "Cell Phone Accessories", "price": 19.99, "rating": 4.5},
    {"asin": "B09ABC002", "title": "Silicone iPhone Case Black", "category": "Cell Phone Accessories", "price": 15.99, "rating": 4.7},
    {"asin": "B09ABC003", "title": "iPhone 15 Protective Cover", "category": "Cell Phone Accessories", "price": 22.99, "rating": 4.6},
    {"asin": "B09ABC004", "title": "Leather iPhone Wallet Case", "category": "Cell Phone Accessories", "price": 29.99, "rating": 4.8},

    # Laptop Stands (wrong category but will match due to low threshold)
    {"asin": "B08XYZ001", "title": "Adjustable Aluminum Laptop Stand", "category": "Computer Accessories", "price": 24.99, "rating": 4.7},
    {"asin": "B08XYZ002", "title": "Portable Laptop Riser Stand", "category": "Computer Accessories", "price": 19.99, "rating": 4.5},
    {"asin": "B08XYZ003", "title": "Ergonomic Laptop Stand", "category": "Computer Accessories", "price": 34.99, "rating": 4.8},

    # Phone Holders (somewhat related)
    {"asin": "B07DEF001", "title": "Car Phone Mount Holder", "category": "Cell Phone Accessories", "price": 12.99, "rating": 4.4},
    {"asin": "B07DEF002", "title": "Desk Phone Stand Holder", "category": "Cell Phone Accessories", "price": 9.99, "rating": 4.3},

    # Completely unrelated
    {"asin": "B06GHI001", "title": "Wireless Bluetooth Headphones", "category": "Electronics", "price": 49.99, "rating": 4.6},
    {"asin": "B06GHI002", "title": "USB-C Charging Cable", "category": "Electronics", "price": 8.99, "rating": 4.2},
]


# ============================================================================
# Mock LLM - Simulating GPT-4 keyword generation
# ============================================================================

def generate_keywords_with_llm(product_title: str, category: str) -> List[str]:
    """Simulate LLM extracting keywords from product title."""
    # In real system, this would call GPT-4
    time.sleep(0.1)  # Simulate API latency

    # Simple keyword extraction
    keywords = []
    title_lower = product_title.lower()

    if "iphone" in title_lower:
        keywords.extend(["phone case", "iPhone case", "protective case"])
    if "case" in title_lower:
        keywords.append("case")
    if "silicone" in title_lower:
        keywords.append("silicone case")
    if "pro" in title_lower:
        keywords.append("iPhone Pro case")

    return keywords or ["phone accessory"]


# ============================================================================
# Mock Search - Simulating Elasticsearch
# ============================================================================

def search_catalog(keywords: List[str], limit: int = 1000) -> List[Dict[str, Any]]:
    """Search product catalog using keywords."""
    time.sleep(0.05)  # Simulate search latency

    # Simple keyword matching
    results = []
    for product in PRODUCT_CATALOG:
        title_lower = product["title"].lower()

        # Check if any keyword matches
        for keyword in keywords:
            if keyword.lower() in title_lower:
                results.append(product.copy())
                break

    # Pad results to simulate finding many candidates
    # In real system, would have thousands of products
    while len(results) < 50 and len(results) < limit:
        results.append(random.choice(PRODUCT_CATALOG).copy())

    return results[:limit]


# ============================================================================
# Category Filter - The Buggy Step!
# ============================================================================

def filter_by_category_similarity(
    candidates: List[Dict[str, Any]],
    target_category: str,
    threshold: float = 0.3  # BUG: This is too low!
) -> List[Dict[str, Any]]:
    """Filter candidates by category similarity."""
    time.sleep(0.02)

    filtered = []
    for candidate in candidates:
        # Simple category similarity (in real system, would use embeddings)
        candidate_category = candidate["category"]

        # Mock similarity score
        if target_category == candidate_category:
            similarity = 1.0
        elif "Accessories" in target_category and "Accessories" in candidate_category:
            similarity = 0.7  # Both are accessories
        elif "Phone" in target_category and "Phone" in candidate_category:
            similarity = 0.9
        else:
            similarity = 0.2  # Different categories

        # BUG: threshold=0.3 is too low, lets laptop stands through (0.7 > 0.3)
        if similarity >= threshold:
            candidate["_category_similarity"] = similarity
            filtered.append(candidate)

    return filtered


# ============================================================================
# Ranking
# ============================================================================

def rank_by_relevance(
    candidates: List[Dict[str, Any]],
    product_title: str,
    boost_price_match: bool = True
) -> List[Dict[str, Any]]:
    """Rank candidates by relevance."""
    time.sleep(0.08)

    # Simple relevance scoring
    for candidate in candidates:
        score = 0.0

        # Title similarity (mock)
        if "case" in product_title.lower() and "case" in candidate["title"].lower():
            score += 0.3
        if "iphone" in product_title.lower() and "iphone" in candidate["title"].lower():
            score += 0.4

        # Category similarity bonus
        if "_category_similarity" in candidate:
            score += candidate["_category_similarity"] * 0.2

        # Price match bonus (BUG: This helps laptop stands rank high!)
        if boost_price_match:
            # Products in similar price range get boosted
            if 15 <= candidate["price"] <= 30:
                score += 0.15

        # Rating bonus
        score += (candidate["rating"] - 4.0) * 0.1

        # Random factor (simulating embedding similarity)
        score += random.uniform(0, 0.1)

        candidate["_relevance_score"] = round(score, 2)

    # Sort by score descending
    ranked = sorted(candidates, key=lambda x: x.get("_relevance_score", 0), reverse=True)
    return ranked


# ============================================================================
# Selection
# ============================================================================

def select_top_competitor(candidates: List[Dict[str, Any]], count: int = 1) -> List[Dict[str, Any]]:
    """Select top N competitors."""
    return candidates[:count]


# ============================================================================
# Main Pipeline - WITH X-Ray Instrumentation
# ============================================================================

def select_competitor_for_product(product_title: str, category: str) -> Dict[str, Any]:
    """
    Main competitor selection pipeline with full X-Ray instrumentation.

    This pipeline has a bug: the category filter threshold is too low (0.3),
    allowing laptop stands to pass through as competitors for phone cases.
    """

    with RunContext(
        pipeline_name="competitor-selection",
        pipeline_version="1.0.0",
        metadata={
            "product_title": product_title,
            "category": category,
            "environment": "demo"
        }
    ) as run:

        # Step 1: Generate Keywords (LLM)
        with run.step("generate_keywords", StepType.LLM) as step:
            step.set_inputs({
                "product_title": product_title,
                "category": category,
                "model": "gpt-4"
            })

            keywords = generate_keywords_with_llm(product_title, category)

            step.set_outputs({
                "keywords": keywords,
                "keyword_count": len(keywords)
            })
            step.set_reasoning("Used GPT-4 to extract relevant search keywords from product title and category")

        # Step 2: Search Catalog
        with run.step("search_catalog", StepType.SEARCH) as step:
            step.set_inputs({
                "keywords": keywords,
                "limit": 1000
            })

            candidates = search_catalog(keywords, limit=1000)

            step.set_candidates(
                candidates_in=0,  # Search step has no input candidates
                candidates_out=len(candidates),
                data=candidates
            )
            step.set_outputs({
                "found": len(candidates)
            })
            step.set_reasoning("Searched product catalog using generated keywords via Elasticsearch")

        # Step 3: Filter by Category (BUGGY STEP!)
        with run.step("filter_by_category", StepType.FILTER) as step:
            threshold = 0.3  # BUG: Too low!

            step.set_inputs({
                "target_category": category,
                "similarity_threshold": threshold,
                "algorithm": "embedding_similarity"
            })

            filtered = filter_by_category_similarity(candidates, category, threshold)

            step.set_candidates(
                candidates_in=len(candidates),
                candidates_out=len(filtered),
                data=filtered
            )
            step.set_filters({
                "category_similarity_threshold": threshold,
                "target_category": category
            })
            step.set_outputs({
                "remaining": len(filtered),
                "filtered_out": len(candidates) - len(filtered)
            })
            step.set_reasoning(f"Filtered by category similarity using embedding distance with threshold {threshold}")

        # Step 4: Rank by Relevance (BUGGY: price boost helps wrong items!)
        with run.step("rank_by_relevance", StepType.RANK) as step:
            step.set_inputs({
                "algorithm": "relevance_score",
                "boost_price_match": True,
                "product_title": product_title
            })

            ranked = rank_by_relevance(filtered, product_title, boost_price_match=True)

            # Store top 100 ranked candidates
            step.set_candidates(
                candidates_in=len(filtered),
                candidates_out=len(ranked),
                data=ranked[:100]
            )
            step.set_outputs({
                "top_score": ranked[0]["_relevance_score"] if ranked else 0,
                "score_range": f"{ranked[-1]['_relevance_score']:.2f} - {ranked[0]['_relevance_score']:.2f}" if ranked else "N/A"
            })
            step.set_reasoning("Ranked by relevance score combining title similarity, category match, price proximity, and ratings")

        # Step 5: Select Best Competitor
        with run.step("select_best", StepType.SELECT) as step:
            step.set_inputs({
                "count": 1
            })

            selected = select_top_competitor(ranked, count=1)

            step.set_candidates(
                candidates_in=len(ranked),
                candidates_out=len(selected),
                data=selected
            )
            step.set_outputs({
                "selected_asin": selected[0]["asin"] if selected else None,
                "selected_title": selected[0]["title"] if selected else None,
                "final_score": selected[0]["_relevance_score"] if selected else 0
            })
            step.set_reasoning("Selected highest-ranked candidate as best competitor")

        # Set final output
        result = selected[0] if selected else None
        run.set_final_output({
            "selected_competitor": {
                "asin": result["asin"],
                "title": result["title"],
                "category": result["category"],
                "price": result["price"],
                "rating": result["rating"],
                "score": result["_relevance_score"]
            } if result else None
        })

        return result


# ============================================================================
# Demo Runner
# ============================================================================

def main():
    print("=" * 70)
    print("X-Ray Competitor Selection Demo")
    print("=" * 70)
    print()

    # Test Case 1: iPhone Case (will likely get wrong result!)
    print("🔍 Test Case 1: Finding competitor for iPhone case")
    print("-" * 70)
    product_title = "iPhone 15 Pro Silicone Case - Black"
    category = "Cell Phone Accessories"

    print(f"Input Product: {product_title}")
    print(f"Category: {category}")
    print()

    result = select_competitor_for_product(product_title, category)

    print("✅ Pipeline completed!")
    print()
    print(f"Selected Competitor:")
    print(f"  ASIN: {result['asin']}")
    print(f"  Title: {result['title']}")
    print(f"  Category: {result['category']}")
    print(f"  Price: ${result['price']}")
    print(f"  Score: {result['_relevance_score']}")
    print()

    # Check if result is wrong
    if "Laptop" in result["title"] or "Computer" in result["category"]:
        print("❌ WRONG MATCH DETECTED!")
        print("   A laptop stand was selected for a phone case!")
        print()
        print("🔍 How to debug with X-Ray:")
        print("   1. Query the API for this run")
        print("   2. Inspect the filter_by_category step")
        print("   3. Check the threshold value and candidates that passed")
        print("   4. See the rank_by_relevance step to see why laptop stand scored high")
        print()

    print("=" * 70)
    print("Trace sent to X-Ray API (check http://127.0.0.1:8001/docs)")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Wait 2 seconds for async trace to be sent")
    print("  2. Query: curl http://127.0.0.1:8001/api/runs?pipeline_name=competitor-selection")
    print("  3. Get details: curl http://127.0.0.1:8001/api/runs/{run_id}")
    print("  4. Inspect the filter_by_category step to find the bug!")
    print()

    # Wait for async send
    time.sleep(2)
    print("✅ Trace should be in X-Ray API now!")


if __name__ == "__main__":
    main()
