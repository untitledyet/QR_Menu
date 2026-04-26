"""Embedding-based utilities: deduplication and library photo matching.

Embeddings beat LLM calls for semantic similarity tasks — they're:
  * deterministic,
  * 50-100x cheaper,
  * significantly more accurate for "find closest match" style work,
  * batchable (2048 inputs per call).

Uses `text-embedding-3-large` (3072-d) for highest quality. Cosine similarity
is computed in pure Python — no numpy dependency required at runtime, though
we use it when available for speed on large libraries.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Iterable, List, Sequence, Tuple

from . import config

logger = logging.getLogger(__name__)


# ── Client factory ────────────────────────────────────────────────────────────

def _get_client():
    from openai import OpenAI
    import httpx
    return OpenAI(
        api_key=config.OPENAI_API_KEY,
        http_client=httpx.Client(
            timeout=httpx.Timeout(
                connect=config.LLM_TIMEOUT_CONNECT,
                read=config.LLM_TIMEOUT_READ,
                write=config.LLM_TIMEOUT_WRITE,
                pool=config.LLM_TIMEOUT_POOL,
            )
        ),
    )


# ── Normalization ─────────────────────────────────────────────────────────────

_STOPWORDS = {
    'classic', 'homemade', 'special', 'best', 'style', 'house',
    'fresh', 'new', 'signature', 'original', 'traditional',
    'large', 'small', 'medium', 'xl', 'xxl', 'mini', 'big',
}

_SIZE_PAREN = re.compile(r'\([^)]*\)')
_MULTI_SPACE = re.compile(r'\s+')


def _normalize(text: str) -> str:
    """Lowercase, strip parentheticals and stopwords — used before embedding."""
    if not text:
        return ''
    s = _SIZE_PAREN.sub(' ', text).lower()
    tokens = [t for t in _MULTI_SPACE.split(s) if t and t not in _STOPWORDS]
    return ' '.join(tokens).strip()


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_texts(texts: Sequence[str]) -> List[List[float]]:
    """Embed a batch of texts. Returns one vector per input, in the same order.

    Empty/whitespace inputs get a zero-vector sentinel so downstream ranking
    returns similarity 0 for them.
    """
    if not texts:
        return []

    try:
        client = _get_client()
    except ImportError:
        logger.warning("[embed] openai not installed")
        return [[0.0]] * len(texts)

    # Replace empty strings with a space — API rejects empty input
    safe_inputs = [(t.strip() or ' ') for t in texts]

    try:
        resp = client.embeddings.create(
            model=config.OPENAI_MODEL_EMBED,
            input=safe_inputs,
        )
        return [d.embedding for d in resp.data]
    except Exception as e:
        logger.warning(f"[embed] failed: {e}")
        # Return zero-vectors so similarity calculations yield 0
        dim = 3072 if 'large' in config.OPENAI_MODEL_EMBED else 1536
        return [[0.0] * dim for _ in texts]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def _cosine_matrix(vectors: List[List[float]]):
    """Try to use numpy for fast pairwise cosine, fall back to pure Python."""
    try:
        import numpy as np
        M = np.asarray(vectors, dtype='float32')
        norms = np.linalg.norm(M, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        N = M / norms
        return N @ N.T
    except ImportError:
        n = len(vectors)
        sim = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i, n):
                s = _cosine(vectors[i], vectors[j])
                sim[i][j] = s
                sim[j][i] = s
        return sim


# ── Deduplication ─────────────────────────────────────────────────────────────

def dedupe_items(items: list, threshold: float = 0.88) -> list:
    """Group near-identical menu items and keep the first (highest-priority) of each group.

    Similarity is computed on normalized name + category so "Caesar Salad" and
    "classic caesar salad" match, while "Chicken Caesar" and "Caesar Salad" stay
    separate (shared substring but different centroid).

    Merges missing price/description/image from duplicates into the kept item.
    Returns a new list of kept items, preserving their original order.
    """
    if len(items) < 2:
        return items

    texts = [
        _normalize(f"{it.get('name', '')} {it.get('category', '')}")
        for it in items
    ]
    vectors = embed_texts(texts)

    if not vectors or len(vectors) != len(items):
        return items

    sim = _cosine_matrix(vectors)
    n = len(items)

    # Greedy: each item joins the earliest cluster it exceeds threshold with.
    cluster_of = [-1] * n
    next_cluster = 0
    for i in range(n):
        for j in range(i):
            if cluster_of[j] == -1:
                continue
            s = sim[i][j] if not hasattr(sim, 'shape') else float(sim[i][j])
            if s >= threshold:
                cluster_of[i] = cluster_of[j]
                break
        if cluster_of[i] == -1:
            cluster_of[i] = next_cluster
            next_cluster += 1

    # Keep the first item per cluster; merge missing fields from duplicates
    primary_of = {}
    for idx, cid in enumerate(cluster_of):
        if cid not in primary_of:
            primary_of[cid] = idx
            continue
        primary = items[primary_of[cid]]
        dup = items[idx]
        for field in ('price', 'description', 'ingredients', 'image'):
            if not primary.get(field) and dup.get(field):
                primary[field] = dup[field]

    kept_indices = sorted(primary_of.values())
    removed = n - len(kept_indices)
    if removed:
        logger.info(f"[embed-dedup] {n} → {len(kept_indices)} items ({removed} removed)")
    return [items[i] for i in kept_indices]


def dedupe_categories(categories: dict, threshold: float = 0.88) -> dict:
    """Apply dedupe_items across a {category: [items]} dict, preserving structure."""
    if not categories:
        return categories
    flat = []
    back_refs = []
    for cat, items in categories.items():
        for it in items:
            flat.append(it)
            back_refs.append(cat)

    kept = dedupe_items(flat, threshold=threshold)
    kept_ids = {id(it) for it in kept}

    result: dict = {}
    for cat, it in zip(back_refs, flat):
        if id(it) in kept_ids:
            result.setdefault(cat, []).append(it)
    return {k: v for k, v in result.items() if v}


# ── Library photo matching ────────────────────────────────────────────────────

def _normalize_names_batch(names: List[str]) -> List[str]:
    """Use GPT-4o to strip qualifiers (counts, sizes, adjectives) from dish names."""
    if not names:
        return names
    try:
        client = _get_client()
        joined = '\n'.join(f'{i}. {n}' for i, n in enumerate(names))
        resp = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {'role': 'system', 'content': (
                    'You are given a numbered list of restaurant dish names. '
                    'For each, return the canonical dish name stripped of all qualifiers: '
                    'quantities ("6 ნაჭრიანი", "500g"), sizes ("დიდი", "პატარა", "large", "small"), '
                    'and purely descriptive adjectives that do not change the dish identity. '
                    'Preserve regional or ingredient-based qualifiers that define the dish '
                    '("ღორის", "ხბოს", "იმერული"). '
                    'Return ONLY a numbered list in the exact same order. No explanation.'
                )},
                {'role': 'user', 'content': joined},
            ],
            temperature=0.0,
            max_tokens=500,
        )
        lines = resp.choices[0].message.content.strip().split('\n')
        result = []
        for i, line in enumerate(lines):
            stripped = re.sub(r'^\d+\.\s*', '', line).strip()
            result.append(stripped if stripped else names[i])
        if len(result) != len(names):
            return names
        return result
    except Exception as e:
        logger.warning(f'[embed] name normalization failed: {e}')
        return names


def match_library_photos(
    menu_items: list,
    library: list,
    threshold: float = 0.82,
) -> List[dict]:
    """For each menu item, find the best library entry above threshold.

    menu_items: list of {i, name, name_ka, name_en, category}
    library:    list of {id, name: {ka, en}, aliases, image_url}

    Returns list of {i, matched_dish_id, matched_image_url, match_confidence,
                     similarity}. Only items at/above `threshold` get a match.
    """
    if not menu_items or not library:
        return []

    # ── Step 1: exact tag matching (priority) ─────────────────
    # Build tag index: normalized tag → library entry
    tag_index: dict = {}
    for entry in library:
        for alias in (entry.get('aliases') or []):
            key = alias.strip().lower()
            if key:
                tag_index[key] = entry
        name = entry.get('name') or {}
        for n in (name.get('ka', ''), name.get('en', '')):
            if n:
                tag_index[n.strip().lower()] = entry

    raw_names = [it.get('name_ka') or it.get('name') or '' for it in menu_items]
    normalized = _normalize_names_batch(raw_names)

    results: List[dict] = []
    unmatched_items: list = []
    for it, norm in zip(menu_items, normalized):
        key = norm.strip().lower()
        entry = tag_index.get(key)
        if entry:
            results.append({
                'i': it.get('i', 0),
                'matched_dish_id': entry.get('id'),
                'matched_image_url': entry.get('image_url', ''),
                'match_confidence': 'high',
                'similarity': 1.0,
            })
        else:
            unmatched_items.append(it)

    if not unmatched_items:
        return results

    # ── Step 2: embedding fallback for unmatched ──────────────
    menu_items = unmatched_items

    def _menu_text(item: dict) -> str:
        parts = [
            item.get('name_en', ''),
            item.get('name_ka', ''),
            item.get('name', ''),
            item.get('category', ''),
        ]
        return _normalize(' '.join(p for p in parts if p))

    def _lib_text(entry: dict) -> str:
        name = entry.get('name') or {}
        parts = [
            name.get('en', '') if isinstance(name, dict) else '',
            name.get('ka', '') if isinstance(name, dict) else '',
            ' '.join(entry.get('aliases') or []),
        ]
        return _normalize(' '.join(p for p in parts if p))

    menu_texts = [_menu_text(it) for it in menu_items]
    lib_texts  = [_lib_text(entry) for entry in library]

    # One combined embedding call is cheaper than two
    all_vecs = embed_texts(menu_texts + lib_texts)
    if not all_vecs:
        return results
    menu_vecs = all_vecs[:len(menu_texts)]
    lib_vecs  = all_vecs[len(menu_texts):]

    for i, mv in enumerate(menu_vecs):
        best_sim = 0.0
        best_idx = -1
        for j, lv in enumerate(lib_vecs):
            s = _cosine(mv, lv)
            if s > best_sim:
                best_sim = s
                best_idx = j

        if best_idx == -1 or best_sim < threshold:
            continue

        entry = library[best_idx]
        confidence = 'high' if best_sim >= 0.90 else 'medium' if best_sim >= threshold else 'low'
        if confidence != 'high':
            continue  # preserve original contract: only assign image when confident

        results.append({
            'i': menu_items[i].get('i', i),
            'matched_dish_id': entry.get('id'),
            'matched_image_url': entry.get('image_url', ''),
            'match_confidence': confidence,
            'similarity': round(best_sim, 4),
        })

    return results
