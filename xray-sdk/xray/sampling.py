"""
X-Ray SDK Sampling Strategies

This module implements smart sampling for large candidate datasets.

Problem:
- Pipelines can process 5,000+ candidates
- Sending all candidate data to API is inefficient (large payload, slow DB, slow queries)

Solution:
- Always capture counts (candidates_in, candidates_out)
- Sample actual candidate data intelligently
- Provide enough data for debugging without overwhelming the system

Reference: IMPLEMENTATION_PLAN.md -> "Sampling Strategy"
"""

import random
from typing import Any, Dict, List, Optional

from .config import get_config


# =============================================================================
# SAMPLING STRATEGIES
# =============================================================================


def sample_candidates(
    candidates: List[Dict[str, Any]],
    max_full_capture: Optional[int] = None,
    sample_size: int = 50,
) -> List[Dict[str, Any]]:
    """
    Sample candidates intelligently for debugging.

    Strategy:
    - If total ≤ max_full_capture: Return all candidates
    - If total > max_full_capture: Sample intelligently
        - First N (see what came in early)
        - Last N (see what survived)
        - Random N from middle (representative sample)

    Args:
        candidates: Full list of candidates
        max_full_capture: Threshold for full capture (defaults to config value)
        sample_size: How many to sample from each section (first/last/middle)

    Returns:
        Sampled list of candidates

    Example:
        # 5000 candidates
        candidates = [{"id": i, "score": ...} for i in range(5000)]

        # Returns ~150 candidates:
        # - First 50
        # - Last 50
        # - 50 random from middle
        sampled = sample_candidates(candidates)
    """
    if max_full_capture is None:
        max_full_capture = get_config().max_candidates_full_capture

    total = len(candidates)

    # If small enough, return all
    if total <= max_full_capture:
        return candidates

    # Otherwise, sample intelligently
    sampled = []

    # First N candidates (see what came in initially)
    first_n = min(sample_size, total)
    sampled.extend(candidates[:first_n])

    # Last N candidates (see what survived filtering)
    last_n = min(sample_size, total)
    if total > sample_size:  # Avoid duplicates if list is small
        sampled.extend(candidates[-last_n:])

    # Random N from middle (representative sample)
    if total > sample_size * 2:  # Only if there's a meaningful middle
        # Get middle section (exclude first and last that we already took)
        middle = candidates[sample_size:-sample_size]
        if len(middle) > sample_size:
            random_sample = random.sample(middle, min(sample_size, len(middle)))
            sampled.extend(random_sample)
        else:
            sampled.extend(middle)

    return sampled


def sample_candidates_head_tail(
    candidates: List[Dict[str, Any]],
    head_size: int = 50,
    tail_size: int = 50,
) -> List[Dict[str, Any]]:
    """
    Simple head + tail sampling.

    Use this when you want to see:
    - What came in (head)
    - What came out (tail)

    Args:
        candidates: Full list of candidates
        head_size: How many from the beginning
        tail_size: How many from the end

    Returns:
        List with first N and last N candidates

    Example:
        # Returns first 50 and last 50
        sampled = sample_candidates_head_tail(candidates)
    """
    total = len(candidates)

    if total <= (head_size + tail_size):
        return candidates

    head = candidates[:head_size]
    tail = candidates[-tail_size:]

    return head + tail


def sample_candidates_random(
    candidates: List[Dict[str, Any]], sample_size: int = 100
) -> List[Dict[str, Any]]:
    """
    Random sampling across the entire dataset.

    Use this when you want a representative sample without bias.

    Args:
        candidates: Full list of candidates
        sample_size: How many to sample

    Returns:
        Randomly sampled candidates

    Example:
        # Returns 100 random candidates
        sampled = sample_candidates_random(candidates, 100)
    """
    total = len(candidates)

    if total <= sample_size:
        return candidates

    return random.sample(candidates, sample_size)


def sample_candidates_stratified(
    candidates: List[Dict[str, Any]],
    strata_key: str,
    samples_per_stratum: int = 10,
) -> List[Dict[str, Any]]:
    """
    Stratified sampling - ensure representation across different groups.

    Use this when candidates have categories/groups and you want to see
    examples from each group.

    Args:
        candidates: Full list of candidates
        strata_key: Key to group by (e.g., "category", "price_range")
        samples_per_stratum: How many samples per group

    Returns:
        Sampled candidates with representation from each group

    Example:
        # Candidates have a "category" field
        candidates = [
            {"id": 1, "category": "electronics", ...},
            {"id": 2, "category": "clothing", ...},
            ...
        ]

        # Returns 10 samples from each category
        sampled = sample_candidates_stratified(candidates, "category", 10)
    """
    # Group candidates by strata
    strata: Dict[Any, List[Dict[str, Any]]] = {}
    for candidate in candidates:
        key = candidate.get(strata_key)
        if key is not None:
            if key not in strata:
                strata[key] = []
            strata[key].append(candidate)

    # Sample from each stratum
    sampled = []
    for stratum_candidates in strata.values():
        if len(stratum_candidates) <= samples_per_stratum:
            sampled.extend(stratum_candidates)
        else:
            sampled.extend(random.sample(stratum_candidates, samples_per_stratum))

    return sampled


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_sampling_summary(
    original_count: int, sampled_count: int
) -> Dict[str, Any]:
    """
    Get a summary of sampling statistics.

    Args:
        original_count: Total number of candidates
        sampled_count: Number of candidates after sampling

    Returns:
        Dictionary with sampling stats

    Example:
        summary = get_sampling_summary(5000, 150)
        # Returns:
        # {
        #     "original_count": 5000,
        #     "sampled_count": 150,
        #     "sampling_rate": 0.03,
        #     "data_reduction": 0.97
        # }
    """
    sampling_rate = sampled_count / original_count if original_count > 0 else 0
    data_reduction = 1 - sampling_rate

    return {
        "original_count": original_count,
        "sampled_count": sampled_count,
        "sampling_rate": sampling_rate,
        "data_reduction": data_reduction,
    }


def should_sample(
    candidates: List[Dict[str, Any]], max_full_capture: Optional[int] = None
) -> bool:
    """
    Determine if sampling is needed.

    Args:
        candidates: List of candidates
        max_full_capture: Threshold (defaults to config value)

    Returns:
        True if sampling should be applied, False otherwise

    Example:
        if should_sample(candidates):
            candidates = sample_candidates(candidates)
    """
    if max_full_capture is None:
        max_full_capture = get_config().max_candidates_full_capture

    return len(candidates) > max_full_capture


# =============================================================================
# INTEGRATION WITH StepContext
# =============================================================================


def auto_sample_candidates(
    candidates: List[Dict[str, Any]],
    strategy: str = "smart",
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Automatically sample candidates based on strategy.

    This is the main function that StepContext will use.

    Args:
        candidates: Full list of candidates
        strategy: Sampling strategy to use
            - "smart" (default): sample_candidates() - first/last/random
            - "head_tail": sample_candidates_head_tail()
            - "random": sample_candidates_random()
            - "stratified": sample_candidates_stratified()
        **kwargs: Additional arguments for specific strategies

    Returns:
        Sampled candidates

    Example:
        # Smart sampling (default)
        sampled = auto_sample_candidates(candidates)

        # Head/tail sampling
        sampled = auto_sample_candidates(candidates, strategy="head_tail", head_size=100)

        # Stratified sampling
        sampled = auto_sample_candidates(candidates, strategy="stratified",
                                        strata_key="category", samples_per_stratum=20)
    """
    if strategy == "smart":
        return sample_candidates(candidates, **kwargs)
    elif strategy == "head_tail":
        return sample_candidates_head_tail(candidates, **kwargs)
    elif strategy == "random":
        return sample_candidates_random(candidates, **kwargs)
    elif strategy == "stratified":
        return sample_candidates_stratified(candidates, **kwargs)
    else:
        # Unknown strategy, default to smart
        return sample_candidates(candidates, **kwargs)
