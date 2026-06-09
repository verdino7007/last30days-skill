"""Shared query preprocessing utilities: noise-word stripping, core subject
extraction, compound term detection, intent classification, and query
expansion. Used by all search modules."""

import re
from typing import Callable, Dict, FrozenSet, List, Optional, Set

# Common multi-word prefixes stripped from all queries (identical across modules)
PREFIXES = [
    'what are the best', 'what is the best', 'what are the latest',
    'what are people saying about', 'what do people think about',
    'how do i use', 'how to use', 'how to',
    'what are', 'what is', 'tips for', 'best practices for',
]

# Multi-word suffixes (used by bird_x)
SUFFIXES = [
    'best practices', 'use cases', 'prompt techniques',
    'prompting techniques', 'prompting tips',
]

# Base noise words shared across most modules
NOISE_WORDS = frozenset({
    # Articles/prepositions/conjunctions
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'and', 'or',
    'of', 'in', 'on', 'for', 'with', 'about', 'to',
    # Question words
    'how', 'what', 'which', 'who', 'why', 'when', 'where',
    'does', 'should', 'could', 'would',
    # Research/meta descriptors
    'best', 'top', 'good', 'great', 'awesome', 'killer',
    'latest', 'new', 'news', 'update', 'updates',
    'trendiest', 'trending', 'hottest', 'hot', 'popular', 'viral',
    'practices', 'features', 'guide', 'tutorial',
    'recommendations', 'advice', 'review', 'reviews',
    'usecases', 'examples', 'comparison', 'versus', 'vs',
    'plugin', 'plugins', 'skill', 'skills', 'tool', 'tools',
    # Prompting meta words
    'prompt', 'prompts', 'prompting', 'techniques', 'tips',
    'tricks', 'methods', 'strategies', 'approaches',
    # Action words
    'using', 'uses', 'use',
    # Misc filler
    'people', 'saying', 'think', 'said', 'lately',
})


def extract_core_subject(
    topic: str,
    *,
    noise: Optional[FrozenSet[str]] = None,
    max_words: Optional[int] = None,
    strip_suffixes: bool = False,
) -> str:
    """Extract core subject from a verbose search query.

    Strips common question/meta prefixes and noise words to produce a
    compact search-friendly query. Platforms customize via parameters.

    Args:
        topic: Raw user query
        noise: Override noise word set (default: NOISE_WORDS)
        max_words: Cap result to N words (default: no cap)
        strip_suffixes: Also strip trailing multi-word suffixes (bird_x uses this)

    Returns:
        Cleaned query string
    """
    text = topic.lower().strip()
    if not text:
        return text

    # Phase 1: Strip multi-word prefixes (longest first, stop after first match)
    for p in PREFIXES:
        if text.startswith(p + ' '):
            text = text[len(p):].strip()
            break

    # Phase 2: Strip multi-word suffixes (opt-in)
    if strip_suffixes:
        for s in SUFFIXES:
            if text.endswith(' ' + s):
                text = text[:-len(s)].strip()
                break

    # Phase 3: Filter individual noise words
    noise_set = noise if noise is not None else NOISE_WORDS
    words = text.split()
    filtered = [w for w in words if w not in noise_set]

    # Apply word cap if requested
    if max_words is not None and filtered:
        filtered = filtered[:max_words]

    result = ' '.join(filtered) if filtered else text
    return result.rstrip('?!.') if not max_words else (result or topic.lower().strip())


def extract_compound_terms(topic: str) -> List[str]:
    """Detect multi-word terms that should be quoted in search queries.

    Identifies:
    - Hyphenated terms: "multi-agent", "vc-backed"
    - Title-cased multi-word names: "Claude Code", "React Native"

    Returns list of terms suitable for quoting (e.g., '"multi-agent"').
    """
    terms: List[str] = []

    # Hyphenated terms
    for match in re.finditer(r'\b\w+-\w+(?:-\w+)*\b', topic):
        terms.append(match.group())

    # Title-cased sequences (2+ capitalized words in a row)
    for match in re.finditer(r'(?:[A-Z][a-z]+\s+){1,}[A-Z][a-z]+', topic):
        terms.append(match.group())

    return terms


# ---------------------------------------------------------------------------
# Per-platform noise-word presets
# ---------------------------------------------------------------------------
# Modules pass these to extract_core_subject(noise=...) instead of defining
# their own frozenset inline. Build from smallest → largest so additions
# are explicit.

SOCIAL_NOISE: FrozenSet[str] = frozenset({
    'best', 'top', 'good', 'great', 'awesome',
    'latest', 'new', 'news', 'update', 'updates',
    'trending', 'hottest', 'popular', 'viral',
    'practices', 'features', 'recommendations', 'advice',
})

VIDEO_NOISE: FrozenSet[str] = SOCIAL_NOISE | frozenset({
    'killer', 'prompt', 'prompts', 'prompting',
    'methods', 'strategies', 'approaches',
})

YOUTUBE_NOISE: FrozenSet[str] = VIDEO_NOISE | frozenset({
    'last', 'days', 'recent', 'recently', 'month', 'week',
    'january', 'february', 'march', 'april', 'may', 'june',
    'july', 'august', 'september', 'october', 'november', 'december',
    '2025', '2026', '2027',
    'music', 'public', 'appearances', 'developments', 'discussions', 'coverage',
})

REDDIT_NOISE: FrozenSet[str] = frozenset({
    'best', 'top', 'good', 'great', 'awesome', 'killer',
    'latest', 'new', 'news', 'update', 'updates',
    'trending', 'hottest', 'popular',
    'practices', 'features', 'tips',
    'recommendations', 'advice',
    'prompt', 'prompts', 'prompting',
    'methods', 'strategies', 'approaches',
    'how', 'to', 'the', 'a', 'an', 'for', 'with',
    'of', 'in', 'on', 'is', 'are', 'what', 'which',
    'guide', 'tutorial', 'using',
})


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

def infer_query_intent(topic: str) -> str:
    """Classify a search topic into an intent category.

    Returns one of: "comparison", "how_to", "opinion", "product",
    "prediction", or "breaking_news" (default fallback).

    Superset of the per-module classifiers previously duplicated in
    reddit, tiktok, instagram, and youtube modules.
    """
    text = topic.lower().strip()
    if re.search(r"\b(vs|versus|compare|difference between)\b", text):
        return "comparison"
    if re.search(
        r"\b(how to|tutorial|guide|setup|step by step|deploy|install"
        r"|configuration|configure|troubleshoot|troubleshooting"
        r"|error|errors|fix|debug)\b",
        text,
    ):
        return "how_to"
    if re.search(r"\b(thoughts on|worth it|should i|opinion|review)\b", text):
        return "opinion"
    if re.search(r"\b(pricing|feature|features|best .* for)\b", text):
        return "product"
    if re.search(r"\b(predict|prediction|odds|forecast|chance)\b", text):
        return "prediction"
    return "breaking_news"


# ---------------------------------------------------------------------------
# Generic query expansion
# ---------------------------------------------------------------------------

def expand_queries(
    topic: str,
    depth: str,
    *,
    extract_core_fn: Callable[[str], str],
    intent_variants: Dict[str, str],
    deep_variant: Optional[str] = None,
    depth_caps: Optional[Dict[str, int]] = None,
) -> List[str]:
    """Build a list of search queries from a topic, parameterized per platform.

    Shared skeleton behind ``expand_tiktok_queries``,
    ``expand_instagram_queries``, ``expand_youtube_queries``, etc.

    Args:
        topic: Raw user query.
        depth: ``"quick"``, ``"default"``, or ``"deep"``.
        extract_core_fn: Platform-specific core-subject extractor
            (e.g. ``lambda t: extract_core_subject(t, noise=VIDEO_NOISE)``).
        intent_variants: Mapping from intent string (e.g. ``"product"``)
            to OR-joined suffix (e.g. ``"review OR haul OR unboxing"``).
            Applied to the first matching intent.
        deep_variant: Optional OR-joined suffix appended only at deep depth
            (e.g. ``"viral OR fyp OR trending"``).
        depth_caps: Per-depth query cap.  Defaults to
            ``{"quick": 1, "default": 2, "deep": 3}``.

    Returns:
        List of query strings, capped by depth.
    """
    core = extract_core_fn(topic)
    queries = [core]

    original_clean = topic.strip().rstrip('?!.')
    if core.lower() != original_clean.lower() and len(original_clean.split()) <= 8:
        queries.append(original_clean)

    qtype = infer_query_intent(topic)
    suffix = intent_variants.get(qtype)
    if suffix:
        queries.append(f"{core} {suffix}")

    if depth == "deep" and deep_variant:
        queries.append(f"{core} {deep_variant}")

    caps = depth_caps or {"quick": 1, "default": 2, "deep": 3}
    cap = caps.get(depth, 2)
    return queries[:cap]
