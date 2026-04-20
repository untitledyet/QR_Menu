"""AI-powered menu analysis using OpenAI GPT-4o."""
import json
import base64
import os
from . import config


def _get_client():
    from openai import OpenAI
    import httpx
    return OpenAI(
        api_key=config.OPENAI_API_KEY,
        http_client=httpx.Client(timeout=60.0),
    )


def _parse_json_response(text: str):
    """Strip markdown fences and parse JSON."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# Photo analysis
# ---------------------------------------------------------------------------

def analyze_menu_photo(image_path: str) -> list:
    """
    Use GPT-4o vision to extract menu items from a printed menu photo.
    Returns list of {name, description, price, category}.
    """
    try:
        client = _get_client()
    except ImportError:
        print("[AI] openai not installed.")
        return []

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = (
        "This is a printed restaurant menu photo. Extract ALL menu items visible.\n"
        "STRICT RULES:\n"
        "- 'name' must be the actual dish or drink name (NOT a price, NOT a number, NOT a category header)\n"
        "- 'price' must be a number only (e.g. '15.00'), empty string if not visible\n"
        "- 'description' is ingredients or description if visible, otherwise empty string\n"
        "- 'category' is the section/category this item belongs to (e.g. სალათები, ცხელი კერძები)\n"
        "- SKIP any entry where name is just a number, a price, or a single letter\n"
        "- SKIP category headers — only include actual dishes/drinks\n"
        "Return ONLY a valid JSON array. Example:\n"
        '[{"name":"ხინკალი","description":"ხორცის ფარში, ცომი","price":"2.00","category":"ხინკალი"}]\n'
        "Return empty array [] if nothing readable."
    )

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=4096,
        )
        items = _parse_json_response(response.choices[0].message.content)
        filtered = []
        for it in items:
            name = it.get("name", "").strip()
            if not name or len(name) < 2:
                continue
            if name.replace(".", "").replace(",", "").isdigit():
                continue
            filtered.append(it)
        print("[AI] Extracted " + str(len(filtered)) + " items from " + os.path.basename(image_path))
        return filtered
    except Exception as e:
        print("[AI] Error analyzing " + os.path.basename(image_path) + ": " + str(e))
        return []


# ---------------------------------------------------------------------------
# Full structured extraction (user photo import)
# ---------------------------------------------------------------------------

def analyze_menu_photo_structured(image_path: str) -> list:
    """
    Extract structured menu items from a photo with category, subcategory,
    ingredients and price. Used for the user-facing photo import feature.
    Returns list of {name, category, subcategory, ingredients, price}.
    """
    try:
        client = _get_client()
    except ImportError:
        return []

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompt = (
        "This is a restaurant menu photo. Extract ALL menu items visible.\n"
        "Return ONLY a valid JSON array. Each element:\n"
        '{"name":"კერძის სახელი","category":"კატეგორია","subcategory":"ქვეკატეგორია_ან_ცარიელი","ingredients":"ინგრედიენტები_ან_ცარიელი","price":"15.00_ან_ცარიელი"}\n'
        "RULES:\n"
        "- name: actual dish or drink name (NOT a price, NOT a number, NOT a header)\n"
        "- category: the section this item belongs to (e.g. სალათები, ცხელი კერძები, სასმელი)\n"
        "- subcategory: sub-section if present (e.g. ვეგეტარიანური, ცხარე), else empty string\n"
        "- ingredients: ingredients or short description visible on menu, else empty string\n"
        "- price: number only (e.g. '12.50'), empty string if not visible\n"
        "- SKIP category/section headers — only include actual dishes and drinks\n"
        "- SKIP entries where name is just a number or price\n"
        "Return empty array [] if nothing readable."
    )

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{img_b64}",
                        "detail": "high",
                    }},
                ],
            }],
            max_tokens=4096,
        )
        items = _parse_json_response(response.choices[0].message.content)
        filtered = []
        for it in items:
            name = it.get("name", "").strip()
            if not name or len(name) < 2:
                continue
            if name.replace(".", "").replace(",", "").isdigit():
                continue
            filtered.append({
                "name": name,
                "category": (it.get("category") or "").strip(),
                "subcategory": (it.get("subcategory") or "").strip(),
                "ingredients": (it.get("ingredients") or "").strip(),
                "price": (it.get("price") or "").strip(),
            })
        print(f"[AI] Structured extract: {len(filtered)} items from {os.path.basename(image_path)}")
        return filtered
    except Exception as e:
        print(f"[AI] Structured extract error: {e}")
        return []


def enrich_missing_ingredients(items: list) -> list:
    """Fill ingredients for items that have none (used after photo import merge)."""
    missing = [it for it in items if not it.get("ingredients")]
    if not missing:
        return items
    try:
        client = _get_client()
    except ImportError:
        return items

    BATCH = 50
    for i in range(0, len(missing), BATCH):
        batch = missing[i:i + BATCH]
        names = [it["name"] for it in batch]
        prompt = (
            "For each Georgian restaurant dish, give typical ingredients in Georgian (3-6 words, comma-separated). "
            "For drinks return empty string. "
            "Return ONLY JSON: {\"dish_name\": \"ingredients\"}.\n"
            "Dishes: " + json.dumps(names, ensure_ascii=False)
        )
        try:
            response = client.chat.completions.create(
                model=config.OPENAI_MODEL_MINI,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            ing_map = _parse_json_response(response.choices[0].message.content)
            for it in batch:
                val = ing_map.get(it["name"], "")
                if val:
                    it["ingredients"] = val
        except Exception as e:
            print(f"[AI] enrich_missing_ingredients error: {e}")

    return items


# ---------------------------------------------------------------------------
# Categorization
# ---------------------------------------------------------------------------

def categorize_items(items: list) -> dict:
    """
    Use GPT-4o to categorize uncategorized menu items.
    Returns dict: {category: [items]}
    """
    try:
        client = _get_client()
    except ImportError:
        return {"Menu": items}

    names = [it.get("name", "") for it in items]
    prompt = (
        "Categorize these Georgian restaurant menu items into logical categories "
        "(e.g. სალათები, ცხელი კერძები, წვნიანები, ცომეული, სასმელი, etc). "
        "Return ONLY valid JSON object where keys are category names and values are arrays of item names.\n"
        "Items: " + json.dumps(names, ensure_ascii=False)
    )

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL_MINI,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        cat_map = _parse_json_response(response.choices[0].message.content)
        name_to_item = {it["name"]: it for it in items}
        result = {}
        for cat, item_names in cat_map.items():
            result[cat] = [name_to_item[n] for n in item_names if n in name_to_item]
        return result
    except Exception as e:
        print("[AI] Categorization error: " + str(e))
        return {"Menu": items}


# ---------------------------------------------------------------------------
# Description enrichment
# ---------------------------------------------------------------------------

def enrich_ingredients(items: list) -> list:
    """
    Use GPT-4o-mini to fill the 'ingredients' field for all items that lack it.
    Uses batching (50 items per call) to stay within token limits.
    Modifies items in-place and returns them.
    """
    # Always fill 'ingredients' — separate from 'description' (which comes from the source)
    to_enrich = [it for it in items if not it.get("ingredients")]
    if not to_enrich:
        return items

    try:
        client = _get_client()
    except ImportError:
        return items

    BATCH = 50
    total_filled = 0

    for i in range(0, len(to_enrich), BATCH):
        batch = to_enrich[i:i + BATCH]
        names = [it["name"] for it in batch]
        prompt = (
            "You are a Georgian restaurant assistant. "
            "For each dish name below, provide its typical ingredients in Georgian language (3-6 words). "
            "Return ONLY valid JSON: {\"dish_name\": \"ingredients as comma-separated string\"}.\n"
            "If a dish is a drink or you don't know it, return an empty string for that key.\n"
            "Dishes: " + json.dumps(names, ensure_ascii=False)
        )

        try:
            response = client.chat.completions.create(
                model=config.OPENAI_MODEL_MINI,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            ing_map = _parse_json_response(response.choices[0].message.content)
            for it in batch:
                val = ing_map.get(it["name"], "")
                if val:
                    it["ingredients"] = val
                    total_filled += 1
        except Exception as e:
            print("[AI] Enrichment batch error: " + str(e))

    print("[AI] Enriched " + str(total_filled) + "/" + str(len(to_enrich)) + " items with ingredients")
    return items


# ---------------------------------------------------------------------------
# AI deduplication
# ---------------------------------------------------------------------------

def ai_deduplicate(categories: dict) -> dict:
    """
    Use GPT-4o-mini to find duplicate items across all categories and remove them.
    Returns cleaned categories dict. Each item keeps its best data.
    Prices from earlier sources (google_text) are never overridden.
    """
    all_items = [(cat, i, it) for cat, items in categories.items() for i, it in enumerate(items)]
    if len(all_items) < 5:
        return categories

    try:
        client = _get_client()
    except ImportError:
        return categories

    names = [it["name"] for _, _, it in all_items]
    prompt = (
        "You are given a list of restaurant menu item names (some may be in Georgian, English, or mixed).\n"
        "Identify groups of DUPLICATE items — same dish with different spellings, transliterations, or language.\n"
        "Return ONLY a JSON array of arrays. Each inner array contains the indices (0-based) of items that are the same dish.\n"
        "Items that are unique (no duplicate) must still appear as single-element arrays.\n"
        "IMPORTANT: only group items you are certain are the same dish. When in doubt, keep them separate.\n"
        "Items:\n" + json.dumps(names, ensure_ascii=False)
    )

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL_MINI,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        groups = _parse_json_response(response.choices[0].message.content)
    except Exception as e:
        print("[AI] Dedup error: " + str(e))
        return categories

    # For each group, keep the first item (highest-priority source) and merge data
    keep_indices = set()
    for group in groups:
        if not group:
            continue
        primary_idx = group[0]
        keep_indices.add(primary_idx)
        primary_item = all_items[primary_idx][2]
        for dup_idx in group[1:]:
            dup_item = all_items[dup_idx][2]
            if not primary_item.get("price") and dup_item.get("price"):
                primary_item["price"] = dup_item["price"]
            if not primary_item.get("description") and dup_item.get("description"):
                primary_item["description"] = dup_item["description"]
            if not primary_item.get("image") and dup_item.get("image"):
                primary_item["image"] = dup_item["image"]

    removed = len(all_items) - len(keep_indices)
    print(f"[AI] Dedup: {len(all_items)} → {len(keep_indices)} items ({removed} duplicates removed)")

    # Rebuild categories keeping only non-duplicate items
    result = {}
    for flat_idx, (cat, item_idx, item) in enumerate(all_items):
        if flat_idx in keep_indices:
            result.setdefault(cat, []).append(item)

    # Remove empty categories
    return {k: v for k, v in result.items() if v}


# ---------------------------------------------------------------------------
# Photo: generate with DALL-E 3
# ---------------------------------------------------------------------------

def generate_dish_photo(dish_name: str, output_dir: str) -> str:
    """
    Generate a professional food photo for a dish using DALL-E 3.
    Saves the image locally and returns the local file path.
    """
    if not dish_name or len(dish_name.strip()) < 2:
        return ""

    try:
        client = _get_client()
    except ImportError:
        return ""

    prompt = (
        "Professional food photography of " + dish_name.strip() + ", "
        "Georgian restaurant dish, top-down view, white plate, "
        "clean background, studio lighting, high quality, appetizing"
    )

    try:
        import requests
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        img_bytes = requests.get(image_url, timeout=30).content

        os.makedirs(output_dir, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in dish_name.strip())[:40]
        fpath = os.path.join(output_dir, "gen_" + safe_name + ".jpg")
        with open(fpath, "wb") as f:
            f.write(img_bytes)
        return fpath
    except Exception as e:
        print("[AI] Image generation error for " + dish_name + ": " + str(e))
        return ""
