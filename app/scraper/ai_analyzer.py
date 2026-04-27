"""AI-powered menu analysis using OpenAI GPT-5.4 (Responses API).

Design goals:
  * Every LLM call goes through the Responses API with `text.format=json_schema`
    so the output is guaranteed-shape and we never hand-parse markdown fences.
  * Vision calls use `detail` / `verbosity` / `reasoning.effort` tuned per task:
      - OCR transcription  → verbosity=high, detail=original
      - Structured parsing → default
      - Quick classification → reasoning.effort=minimal
  * Deduplication and library-photo matching use embeddings (see embeddings.py),
    not the LLM — semantic similarity is what those tasks actually need.
  * Retries with backoff for transient errors; empty lists/dicts on hard failure.

Public API (backward compatible):
  analyze_menu_photo(path) -> list
  analyze_menu_photo_structured(path, event_cb=None) -> list
  assign_global_categories(items, global_cats, global_subcats) -> list
  enrich_missing_ingredients(items) -> list
  translate_items_bilingual(items) -> list
  match_library_photos_ai(menu_items, library) -> list        # embedding-backed
  categorize_items(items) -> dict
  enrich_ingredients(items) -> list
  ai_deduplicate(categories) -> dict                          # embedding-backed
  generate_dish_photo(dish_name, output_dir) -> str
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from typing import Any, Callable, Iterable, List, Optional

from . import config
from .image_preprocessor import prepare_for_vision

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Client + retry helpers
# ═════════════════════════════════════════════════════════════════════════════

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


def _with_retry(fn: Callable[[], Any], *, label: str, max_retries: Optional[int] = None) -> Any:
    """Run fn() with exponential backoff on transient errors."""
    if max_retries is None:
        max_retries = config.LLM_MAX_RETRIES
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            retriable = any(s in msg for s in (
                'timeout', 'timed out', 'rate limit', 'overloaded',
                '429', '500', '502', '503', '504',
            ))
            if attempt >= max_retries or not retriable:
                break
            delay = min(2 ** attempt, 8) + 0.25 * attempt
            logger.warning(f"[AI:{label}] retry {attempt + 1}/{max_retries} after {delay:.1f}s — {e}")
            time.sleep(delay)
    logger.warning(f"[AI:{label}] failed: {last_err}")
    raise last_err if last_err else RuntimeError("unknown error")


# ═════════════════════════════════════════════════════════════════════════════
# JSON Schemas (used with text.format={"type":"json_schema",...})
# ═════════════════════════════════════════════════════════════════════════════

# Vision photo extraction — flat list per photo
_SCHEMA_VISION_ITEMS = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "price": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": ["name", "price", "description", "category"],
            },
        }
    },
    "required": ["items"],
}

# Hierarchical parsing from raw OCR text
_SCHEMA_HIERARCHICAL = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "subcategories": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string"},
                                "items": {
                                    "type": "array",
                                    "items": {"$ref": "#/$defs/item"},
                                },
                            },
                            "required": ["name", "items"],
                        },
                    },
                    "items": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/item"},
                    },
                },
                "required": ["name", "subcategories", "items"],
            },
        }
    },
    "required": ["categories"],
    "$defs": {
        "item": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "price": {"type": ["string", "null"]},
                "description": {"type": "string"},
                "variants": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "price": {"type": ["string", "null"]},
                        },
                        "required": ["name", "price"],
                    },
                },
            },
            "required": ["name", "price", "description", "variants"],
        }
    },
}

# Category mapping
_SCHEMA_CATEGORY_MAP = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "mapping": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "input": {"type": "string"},
                    "matched": {"type": "string"},
                },
                "required": ["input", "matched"],
            },
        }
    },
    "required": ["mapping"],
}

# Ingredient enrichment
_SCHEMA_INGREDIENTS = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "i": {"type": "integer"},
                    "extracted": {"type": "array", "items": {"type": "string"}},
                    "inferred":  {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                },
                "required": ["i", "extracted", "inferred", "confidence"],
            },
        }
    },
    "required": ["results"],
}

# Bilingual translation
_SCHEMA_BILINGUAL = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "i": {"type": "integer"},
                    "name_ka": {"type": "string"},
                    "name_en": {"type": "string"},
                    "category_ka": {"type": "string"},
                    "category_en": {"type": "string"},
                    "description_ka": {"type": "string"},
                    "description_en": {"type": "string"},
                    "ingredients_ka": {"type": "string"},
                    "ingredients_en": {"type": "string"},
                },
                "required": [
                    "i", "name_ka", "name_en",
                    "category_ka", "category_en",
                    "description_ka", "description_en",
                    "ingredients_ka", "ingredients_en",
                ],
            },
        }
    },
    "required": ["results"],
}

# Simple ingredient dict (dish → ingredients string)
_SCHEMA_DISH_INGREDIENTS = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "ingredients": {"type": "string"},
                },
                "required": ["name", "ingredients"],
            },
        }
    },
    "required": ["results"],
}

# Categorization
_SCHEMA_CATEGORIZE = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "buckets": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["category", "items"],
            },
        }
    },
    "required": ["buckets"],
}


# ═════════════════════════════════════════════════════════════════════════════
# Low-level call wrappers (Responses API)
# ═════════════════════════════════════════════════════════════════════════════

def _structured_call(
    *,
    model: str,
    prompt: str,
    schema_name: str,
    schema: dict,
    image_data_url: Optional[str] = None,
    image_detail: str = "auto",
    verbosity: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    label: str = "structured",
) -> dict:
    """Single entry point for structured LLM calls via Responses API.

    Returns parsed dict conforming to `schema`. Raises on failure.
    """
    client = _get_client()

    user_content: list = [{"type": "input_text", "text": prompt}]
    if image_data_url:
        user_content.append({
            "type": "input_image",
            "image_url": image_data_url,
            "detail": image_detail,
        })

    text_cfg: dict = {
        "format": {
            "type": "json_schema",
            "name": schema_name,
            "schema": schema,
            "strict": True,
        }
    }
    if verbosity:
        text_cfg["verbosity"] = verbosity

    kwargs: dict = {
        "model": model,
        "input": [{"role": "user", "content": user_content}],
        "text": text_cfg,
    }
    if reasoning_effort:
        kwargs["reasoning"] = {"effort": reasoning_effort}

    def _call():
        resp = client.responses.create(**kwargs)
        raw = (resp.output_text or "").strip()
        return json.loads(raw)

    return _with_retry(_call, label=label)


def _vision_ocr_text(image_data_url: str, *, model: Optional[str] = None) -> str:
    """Plain-text transcription of an image (high verbosity, original detail)."""
    client = _get_client()

    def _call():
        resp = client.responses.create(
            model=model or config.OPENAI_MODEL_VISION,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text",
                     "text": "Transcribe every piece of text visible in this image exactly as it appears. "
                             "Preserve layout cues (line breaks, columns, bullets) with plain ASCII "
                             "(newlines, ' - ', indentation). Do not summarize, explain, or add commentary."},
                    {"type": "input_image", "image_url": image_data_url, "detail": "original"},
                ],
            }],
            text={"verbosity": "high"},
        )
        return (resp.output_text or "").strip()

    return _with_retry(_call, label="ocr")


def _image_to_data_url(image_path: str) -> str:
    data, mime = prepare_for_vision(image_path)
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


# ═════════════════════════════════════════════════════════════════════════════
# 1. Vision — single-photo extraction
# ═════════════════════════════════════════════════════════════════════════════

_VISION_EXTRACT_PROMPT = """You extract structured menu data from restaurant photos.

# Task
Return every dish or drink visible in the image.

# Per-item schema
- name: the dish name only (e.g. "ხინკალი", "Caesar Salad")
- price: numeric string only (e.g. "15.00") or "" when no price is shown
- description: ingredients or subtitle text if shown, otherwise ""
- category: the section header this item sits under (e.g. "სალათები", "Pizza")

# What counts as an item
INCLUDE:
  • any dish or drink with a name, even if the price is missing
  • each variant of a dish (e.g. "Small"/"Large") as its own item — append the
    variant to the name: "Pizza Margherita (Small)"

EXCLUDE:
  • standalone prices, page numbers, addresses, phone numbers
  • pure category headers without a dish
  • decorative slogans or promotional text

# Examples
"ხინკალი ხორცის — 2.00" under the header "ხინკალი"
  → {"name":"ხინკალი ხორცის","price":"2.00","description":"","category":"ხინკალი"}

"Caesar Salad · Romaine, parmesan, croutons · 25 ₾" under "Salads"
  → {"name":"Caesar Salad","price":"25","description":"Romaine, parmesan, croutons","category":"Salads"}

"Pizza Margherita  S 12  L 18"
  → two items: "Pizza Margherita (S)" price 12, "Pizza Margherita (L)" price 18

If the photo is unreadable or contains no menu, return {"items": []}."""


def analyze_menu_photo(image_path: str) -> list:
    """Extract menu items from a single printed-menu photo.

    Returns list of {name, description, price, category}.
    """
    try:
        data_url = _image_to_data_url(image_path)
    except Exception as e:
        logger.warning(f"[AI] image prep failed for {os.path.basename(image_path)}: {e}")
        return []

    try:
        parsed = _structured_call(
            model=config.OPENAI_MODEL_VISION,
            prompt=_VISION_EXTRACT_PROMPT,
            schema_name="menu_extraction",
            schema=_SCHEMA_VISION_ITEMS,
            image_data_url=data_url,
            image_detail="auto",
            verbosity="high",
            label="photo_extract",
        )
    except Exception:
        return []

    raw_items = parsed.get("items", [])
    filtered = []
    for it in raw_items:
        name = (it.get("name") or "").strip()
        if len(name) < 2:
            continue
        if name.replace(".", "").replace(",", "").isdigit():
            continue
        filtered.append({
            "name": name,
            "price": (it.get("price") or "").strip(),
            "description": (it.get("description") or "").strip(),
            "category": (it.get("category") or "").strip(),
        })
    logger.info(f"[AI] Extracted {len(filtered)} items from {os.path.basename(image_path)}")
    return filtered


# ═════════════════════════════════════════════════════════════════════════════
# 2. Two-step OCR → hierarchical parse (user photo import path)
# ═════════════════════════════════════════════════════════════════════════════

_PARSE_SYSTEM_RULES = """You convert raw OCR text from a restaurant menu into a clean, hierarchical JSON structure.

# Output shape (strict)
{
  "categories": [
    {
      "name": "<category>",
      "subcategories": [
        {"name": "<sub>", "items": [ <item>, ... ]}
      ],
      "items": [ <item>, ... ]
    }
  ]
}
where <item> is:
  {
    "name":        "<dish name>",
    "price":       "<numeric string>" | null,
    "description": "<ingredients/subtitle>" | "",
    "variants":    [{"name": "<label>", "price": "<numeric string>" | null}]
  }

# Handling messy input
1. Plain lists, nested categories, handwritten text, typos — all fair game
2. Price formats ("10", "10₾", "GEL 10", "$5") → extract numeric string only
3. Size/volume variants (Small/Large/XL, 0.33L/0.5L) → fill `variants`, leave top-level price empty
4. Filling/ingredient variants (ხორცის/ყველის, meat/cheese, chicken/mushroom) → treat as SEPARATE items, each with the qualifier in its name (e.g. "პელმენი ქოთანში (ხორცის)" and "პელმენი ქოთანში (ყველის)"). Do NOT collapse them into one item with variants.
5. If no explicit categories exist, infer sensible ones (Drinks, Mains, Desserts…)
6. When uncertain about placement, use "Other"
7. De-duplicate items that appear multiple times with the exact same name and filling
7. Ignore addresses, phone numbers, slogans, service-charge lines

# Hard rules
- Never hallucinate dishes the OCR text does not reference.
- Never invent prices — missing price = null.
- Fix obvious typos but preserve culturally-specific names (do not translate).
- Keep subcategories=[] when none exist; keep items=[] when a category only has sub-items.
- variants=[] when there are no size/option variants.

# Raw OCR text follows below.
"""


def analyze_menu_photo_structured(image_path: str, event_cb=None) -> list:
    """Two-step extraction: OCR transcription → hierarchical parse → flat item list.

    event_cb(kind, **data) fires on 'ocr_done' and 'parse_done' when provided.
    Returns flat list of {name, category, subcategory, ingredients, price}.
    """
    try:
        data_url = _image_to_data_url(image_path)
    except Exception as e:
        logger.warning(f"[AI] image prep failed for {os.path.basename(image_path)}: {e}")
        return []

    # ── Step 1: OCR ──────────────────────────────────────────────────────────
    try:
        raw_text = _vision_ocr_text(data_url)
    except Exception as e:
        logger.warning(f"[AI] OCR error for {os.path.basename(image_path)}: {e}")
        return []

    if not raw_text or len(raw_text) < 10:
        return []

    logger.info(f"[AI] OCR extracted {len(raw_text)} chars from {os.path.basename(image_path)}")
    if event_cb:
        try:
            preview = raw_text[:700] + ('…' if len(raw_text) > 700 else '')
            event_cb('ocr_done', text=preview)
        except Exception:
            pass

    # ── Step 2: Hierarchical parse ───────────────────────────────────────────
    try:
        parsed = _structured_call(
            model=config.OPENAI_MODEL_REASON,
            prompt=_PARSE_SYSTEM_RULES + "\n" + raw_text,
            schema_name="menu_hierarchy",
            schema=_SCHEMA_HIERARCHICAL,
            label="hierarchical_parse",
        )
    except Exception as e:
        logger.warning(f"[AI] Parse error for {os.path.basename(image_path)}: {e}")
        return []

    flat: list = []
    for cat in parsed.get("categories", []):
        cat_name = (cat.get("name") or "").strip()

        def _flush(items_list, sub_name=""):
            for it in (items_list or []):
                name = (it.get("name") or "").strip()
                if len(name) < 2:
                    continue
                if name.replace(".", "").replace(",", "").isdigit():
                    continue
                variants = it.get("variants") or []
                if variants:
                    for v in variants:
                        vname = f"{name} ({v.get('name', '')})" if v.get("name") else name
                        flat.append({
                            "name": vname,
                            "category": cat_name,
                            "subcategory": sub_name,
                            "ingredients": (it.get("description") or "").strip(),
                            "price": str(v.get("price") or "").strip(),
                        })
                else:
                    flat.append({
                        "name": name,
                        "category": cat_name,
                        "subcategory": sub_name,
                        "ingredients": (it.get("description") or "").strip(),
                        "price": str(it.get("price") or "").strip(),
                    })

        _flush(cat.get("items", []))
        for sub in (cat.get("subcategories") or []):
            _flush(sub.get("items", []), (sub.get("name") or "").strip())

    logger.info(f"[AI] Parsed {len(flat)} items from {os.path.basename(image_path)}")
    if event_cb:
        try:
            event_cb('parse_done',
                     items=[{'name': it['name'], 'category': it.get('category', '')} for it in flat],
                     count=len(flat))
        except Exception:
            pass
    return flat


# ═════════════════════════════════════════════════════════════════════════════
# 3. Category assignment — map extracted → GlobalLibrary
# ═════════════════════════════════════════════════════════════════════════════

_CATEGORY_MAP_PROMPT = """You classify restaurant menu items into a fixed global taxonomy.

For each input name, pick the SINGLE best-fitting category from the allowed list.
If nothing fits well, pick the most general applicable category from the list — never
invent a new category.

Return a mapping array where each entry has:
  - "input":   the original input string
  - "matched": the exact category name from the allowed list (case-sensitive)
"""


def assign_global_categories(items: list, global_cats: list, global_subcats: list) -> list:
    """Populate category_id / subcategory_id on each item from the GlobalLibrary."""
    if not items:
        return items

    cat_by_name = {c["name"].lower(): c for c in global_cats}
    sub_by_name = {s["name"].lower(): s for s in global_subcats}
    cat_names = [c["name"] for c in global_cats]
    sub_names = [s["name"] for s in global_subcats]

    unique_cats = sorted({(it.get("category") or "").strip() for it in items if it.get("category")})
    unique_subs = sorted({(it.get("subcategory") or "").strip() for it in items if it.get("subcategory")})
    items_no_cat = sorted({(it.get("name") or "").strip() for it in items if not it.get("category")})

    cat_mapping: dict = {}
    sub_mapping: dict = {}

    # Step 1: categories
    to_map = [s for s in (unique_cats + items_no_cat) if s]
    if to_map and cat_names:
        prompt = (
            _CATEGORY_MAP_PROMPT
            + "\nAllowed categories:\n" + json.dumps(cat_names, ensure_ascii=False)
            + "\n\nInputs to classify:\n" + json.dumps(to_map, ensure_ascii=False)
        )
        try:
            parsed = _structured_call(
                model=config.OPENAI_MODEL_FAST,
                prompt=prompt,
                schema_name="category_mapping",
                schema=_SCHEMA_CATEGORY_MAP,
                reasoning_effort="low",
                label="cat_map",
            )
            for row in parsed.get("mapping", []):
                inp = (row.get("input") or "").strip()
                match = cat_by_name.get((row.get("matched") or "").strip().lower())
                if inp and match:
                    cat_mapping[inp.lower()] = match
            logger.info(f"[AI] Category mapping: {len(cat_mapping)} matched")
        except Exception as e:
            logger.warning(f"[AI] Category mapping failed: {e}")

    # Step 2: subcategories
    if unique_subs and sub_names:
        prompt = (
            _CATEGORY_MAP_PROMPT
            + "\nAllowed subcategories:\n" + json.dumps(sub_names, ensure_ascii=False)
            + "\n\nInputs to classify:\n" + json.dumps(unique_subs, ensure_ascii=False)
        )
        try:
            parsed = _structured_call(
                model=config.OPENAI_MODEL_FAST,
                prompt=prompt,
                schema_name="subcategory_mapping",
                schema=_SCHEMA_CATEGORY_MAP,
                reasoning_effort="low",
                label="subcat_map",
            )
            for row in parsed.get("mapping", []):
                inp = (row.get("input") or "").strip()
                match = sub_by_name.get((row.get("matched") or "").strip().lower())
                if inp and match:
                    sub_mapping[inp.lower()] = match
            logger.info(f"[AI] Subcategory mapping: {len(sub_mapping)} matched")
        except Exception as e:
            logger.warning(f"[AI] Subcategory mapping failed: {e}")

    # Step 3: apply
    for it in items:
        raw_cat = (it.get("category") or "").strip()
        cat_entry = cat_mapping.get(raw_cat.lower()) or cat_mapping.get((it.get("name") or "").lower())
        if cat_entry:
            it["category"] = cat_entry["name"]
            it["category_id"] = cat_entry["id"]
        else:
            it.setdefault("category", raw_cat or "სხვა")
            it["category_id"] = None

        raw_sub = (it.get("subcategory") or "").strip()
        if raw_sub:
            sub_entry = sub_mapping.get(raw_sub.lower())
            if sub_entry:
                it["subcategory"] = sub_entry["name"]
                it["subcategory_id"] = sub_entry["id"]
            else:
                it["subcategory_id"] = None
        else:
            it["subcategory_id"] = None

    return items


# ═════════════════════════════════════════════════════════════════════════════
# 4. Ingredient enrichment (detailed — extracted vs inferred + confidence)
# ═════════════════════════════════════════════════════════════════════════════

_ENRICH_PROMPT = """You add ingredient data to restaurant menu items.

For each item:
  * extracted:  ingredients the description explicitly states
  * inferred:   ingredients a knowledgeable chef would expect for that dish,
                when not explicitly stated
  * confidence: high | medium | low

Rules:
  * Drinks (juices, sodas, cocktails, beer, wine, coffee, tea): return extracted=[] and inferred=[]
  * Do not hallucinate exotic ingredients a typical recipe would not use
  * Use the dish's native culinary vocabulary
  * Output one result object per input index, in the same order, always keyed by "i"
"""


def enrich_missing_ingredients(items: list) -> list:
    """Fill 'ingredients' for items missing it, flagging extracted vs inferred."""
    missing = [it for it in items if not it.get("ingredients")]
    if not missing:
        return items

    BATCH = 50
    for i in range(0, len(missing), BATCH):
        batch = missing[i:i + BATCH]
        payload = [
            {"i": j, "name": (it.get("name") or ""), "description": (it.get("description") or "")}
            for j, it in enumerate(batch)
        ]
        prompt = _ENRICH_PROMPT + "\nItems:\n" + json.dumps(payload, ensure_ascii=False)
        try:
            parsed = _structured_call(
                model=config.OPENAI_MODEL_FAST,
                prompt=prompt,
                schema_name="ingredient_enrichment",
                schema=_SCHEMA_INGREDIENTS,
                reasoning_effort="low",
                label="ingr_enrich",
            )
        except Exception:
            continue
        result_map = {r["i"]: r for r in parsed.get("results", []) if isinstance(r, dict)}
        for j, it in enumerate(batch):
            r = result_map.get(j, {})
            all_ings = (r.get("extracted") or []) + (r.get("inferred") or [])
            if all_ings:
                it["ingredients"] = ", ".join(str(x) for x in all_ings if x)

    return items


# ═════════════════════════════════════════════════════════════════════════════
# 5. Bilingual translation
# ═════════════════════════════════════════════════════════════════════════════

_BILINGUAL_PROMPT = """You normalize and translate restaurant menu items into Georgian (ka) AND English (en).

For every input, produce BOTH translations regardless of the source language.

# Hard rules
1. Food-industry STANDARD translations, not literal:
     ხაჭაპური ↔ Khachapuri      (NOT "cheese bread")
     ხინკალი ↔ Khinkali         (NOT "dumplings")
     შაურმა ↔ Shawarma
     ცეზარი ↔ Caesar Salad
2. International dishes keep their canonical name: Pizza, Burger, Pasta, Tiramisu.
3. Local/traditional dishes: transliterate into English, do not over-explain.
4. Generic names translate meaningfully ("ქათმის სალათი" → "Chicken Salad").
5. Descriptions: natural paraphrase, not word-by-word.
6. Ingredients: standard culinary terms ("ყველი" → "cheese", "საქონლის ხორცი" → "beef").
7. Keep capitalization: English Title Case for names; Georgian natural.
8. Fix obvious typos before translating.
9. Do not invent new dishes or change meaning.
10. Keep the SAME index for each output (i) as in the input.

# Output
Return a results array — one object per input item, each with:
  i, name_ka, name_en, category_ka, category_en,
  description_ka, description_en, ingredients_ka, ingredients_en
"""


def translate_items_bilingual(items: list) -> list:
    """Populate name_ka, name_en, ingredients_ka, ingredients_en on every item.

    Deduplicates by (name, category, description, ingredients) tuple so repeated
    dishes hit the LLM once.
    """
    if not items:
        return items

    # Dedup payload
    seen: dict = {}
    payload: list = []
    key_for: list = []
    for idx, it in enumerate(items):
        key = (
            (it.get("name") or "").strip().lower(),
            (it.get("category") or "").strip().lower(),
            (it.get("description") or "").strip().lower(),
            (it.get("ingredients") or "").strip().lower(),
        )
        key_for.append(key)
        if key in seen:
            continue
        seen[key] = len(payload)
        payload.append({
            "i": seen[key],
            "name": it.get("name", ""),
            "category": it.get("category", ""),
            "description": it.get("description", ""),
            "ingredients": it.get("ingredients", ""),
        })

    BATCH = 40
    translations: dict = {}
    for start in range(0, len(payload), BATCH):
        batch = payload[start:start + BATCH]
        # Rebase indices inside the batch so i=0..len(batch)-1
        local = [{**row, "i": k} for k, row in enumerate(batch)]
        prompt = _BILINGUAL_PROMPT + "\n\nInput:\n" + json.dumps(local, ensure_ascii=False)
        try:
            parsed = _structured_call(
                model=config.OPENAI_MODEL_FAST,
                prompt=prompt,
                schema_name="bilingual",
                schema=_SCHEMA_BILINGUAL,
                label="bilingual",
            )
        except Exception:
            continue
        for r in parsed.get("results", []):
            if not isinstance(r, dict):
                continue
            local_i = r.get("i")
            if local_i is None or local_i >= len(batch):
                continue
            global_i = batch[local_i]["i"]
            translations[global_i] = r

    # Apply back to every input item
    for idx, it in enumerate(items):
        key = key_for[idx]
        tid = seen.get(key)
        r = translations.get(tid) if tid is not None else None
        if r:
            it["name_ka"] = (r.get("name_ka") or it.get("name", "")).strip()
            it["name_en"] = (r.get("name_en") or it.get("name", "")).strip()
            it["category_en"] = (r.get("category_en") or it.get("category", "")).strip()
            it["ingredients_ka"] = (r.get("ingredients_ka") or it.get("ingredients", "")).strip()
            it["ingredients_en"] = (r.get("ingredients_en") or "").strip()
        else:
            it.setdefault("name_ka", it.get("name", ""))
            it.setdefault("name_en", it.get("name", ""))
            it.setdefault("category_en", it.get("category", ""))
            it.setdefault("ingredients_ka", it.get("ingredients", ""))
            it.setdefault("ingredients_en", "")

    logger.info(f"[AI] Bilingual translation done for {len(items)} items "
                f"({len(payload)} unique)")
    return items


# ═════════════════════════════════════════════════════════════════════════════
# 6. Library photo matching — embedding-backed
# ═════════════════════════════════════════════════════════════════════════════

def match_library_photos_ai(menu_items: list, library: list) -> list:
    """Find library photos for menu items using semantic similarity.

    Kept under the `_ai` suffix for back-compat but implemented with embeddings —
    vastly more accurate and cheaper than an LLM call for this use case.
    """
    from .embeddings import match_library_photos
    if not menu_items or not library:
        return []
    try:
        return match_library_photos(menu_items, library, threshold=0.82)
    except Exception as e:
        logger.warning(f"[AI] match_library_photos_ai failed: {e}")
        return []


# ═════════════════════════════════════════════════════════════════════════════
# 7. Categorization (when no categories came from the source)
# ═════════════════════════════════════════════════════════════════════════════

_CATEGORIZE_PROMPT = """Group Georgian restaurant menu items into logical sections.

Typical categories: სალათები, ცხელი კერძები, წვნიანები, ცომეული, სასმელი,
სადილი, დესერტი, საუზმე — but infer the best fit for each input.

Output buckets: each bucket has a "category" name and an "items" array containing
exact item names from the input. Every input name must appear in exactly one bucket.
"""


def categorize_items(items: list) -> dict:
    """Return {category_name: [items]} by grouping items via LLM."""
    if not items:
        return {}

    names = [it.get("name", "") for it in items]
    prompt = _CATEGORIZE_PROMPT + "\n\nItems:\n" + json.dumps(names, ensure_ascii=False)

    try:
        parsed = _structured_call(
            model=config.OPENAI_MODEL_FAST,
            prompt=prompt,
            schema_name="categorize",
            schema=_SCHEMA_CATEGORIZE,
            reasoning_effort="low",
            label="categorize",
        )
    except Exception as e:
        logger.warning(f"[AI] Categorization failed: {e}")
        return {"Menu": items}

    name_to_item = {it["name"]: it for it in items}
    result: dict = {}
    assigned: set = set()
    for bucket in parsed.get("buckets", []):
        cat = (bucket.get("category") or "").strip() or "სხვა"
        grouped = []
        for n in bucket.get("items", []):
            if n in name_to_item and n not in assigned:
                grouped.append(name_to_item[n])
                assigned.add(n)
        if grouped:
            result[cat] = grouped

    # Ensure every item lands somewhere
    leftovers = [it for it in items if it["name"] not in assigned]
    if leftovers:
        result.setdefault("სხვა", []).extend(leftovers)
    return result


# ═════════════════════════════════════════════════════════════════════════════
# 8. Simple ingredient enrichment (dish name → ingredients string)
# ═════════════════════════════════════════════════════════════════════════════

_SIMPLE_INGR_PROMPT = """You produce typical ingredient strings for restaurant dishes.

For each dish name, output ingredients as a short Georgian comma-separated string
(3-6 items). If the item is a drink or you are unsure, return an empty string.
Return one result object per input, preserving the input name exactly.
"""


def enrich_ingredients(items: list) -> list:
    """Fill 'ingredients' for items lacking it, via a simpler name-only prompt."""
    to_enrich = [it for it in items if not it.get("ingredients")]
    if not to_enrich:
        return items

    BATCH = 50
    total_filled = 0
    for i in range(0, len(to_enrich), BATCH):
        batch = to_enrich[i:i + BATCH]
        names = [it["name"] for it in batch]
        prompt = _SIMPLE_INGR_PROMPT + "\n\nDishes:\n" + json.dumps(names, ensure_ascii=False)
        try:
            parsed = _structured_call(
                model=config.OPENAI_MODEL_FAST,
                prompt=prompt,
                schema_name="dish_ingredients",
                schema=_SCHEMA_DISH_INGREDIENTS,
                reasoning_effort="low",
                label="simple_ingr",
            )
        except Exception:
            continue
        ingr_map = {r["name"]: r.get("ingredients", "") for r in parsed.get("results", []) if isinstance(r, dict)}
        for it in batch:
            val = ingr_map.get(it["name"], "")
            if val:
                it["ingredients"] = val
                total_filled += 1

    logger.info(f"[AI] Enriched {total_filled}/{len(to_enrich)} items with ingredients")
    return items


# ═════════════════════════════════════════════════════════════════════════════
# 9. Deduplication — embedding-backed
# ═════════════════════════════════════════════════════════════════════════════

def ai_deduplicate(categories: dict) -> dict:
    """Remove duplicate dishes across categories using semantic embeddings.

    Same public contract as the original LLM version, but now computed with
    `text-embedding-3-large` + cosine similarity (deterministic + cheap).
    """
    from .embeddings import dedupe_categories
    if not categories:
        return categories
    try:
        return dedupe_categories(categories, threshold=0.88)
    except Exception as e:
        logger.warning(f"[AI] embedding dedup failed: {e}")
        return categories


# ═════════════════════════════════════════════════════════════════════════════
# 10. Image generation — gpt-image-1 (newer than DALL·E 3)
# ═════════════════════════════════════════════════════════════════════════════

def generate_dish_photo(dish_name: str, output_dir: str) -> str:
    """Generate a professional food photo and save to `output_dir`, return local path."""
    if not dish_name or len(dish_name.strip()) < 2:
        return ""

    prompt = (
        f"Professional food photography of {dish_name.strip()}, "
        "Georgian restaurant dish, top-down 45-degree angle on a matte white plate, "
        "clean neutral background, soft studio lighting, shallow depth of field, "
        "crisp focus on the food, appetizing, editorial magazine quality."
    )

    try:
        client = _get_client()
    except ImportError:
        return ""

    def _call():
        return client.images.generate(
            model=config.OPENAI_MODEL_IMAGE_GEN,
            prompt=prompt,
            size="1024x1024",
            n=1,
        )

    try:
        response = _with_retry(_call, label="image_gen")
    except Exception as e:
        logger.warning(f"[AI] Image generation failed for {dish_name}: {e}")
        return ""

    # gpt-image-1 returns b64_json by default; DALL·E 3 returns url.
    entry = response.data[0]
    img_bytes: Optional[bytes] = None
    try:
        if getattr(entry, "b64_json", None):
            img_bytes = base64.b64decode(entry.b64_json)
        elif getattr(entry, "url", None):
            import requests as _req
            img_bytes = _req.get(entry.url, timeout=30).content
    except Exception as e:
        logger.warning(f"[AI] Image fetch failed: {e}")
        return ""

    if not img_bytes:
        return ""

    try:
        os.makedirs(output_dir, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in dish_name.strip())[:40]
        fpath = os.path.join(output_dir, f"gen_{safe_name}.png")
        with open(fpath, "wb") as f:
            f.write(img_bytes)
        return fpath
    except Exception as e:
        logger.warning(f"[AI] Image save failed: {e}")
        return ""
