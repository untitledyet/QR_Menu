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
        http_client=httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=240.0, write=60.0, pool=10.0)
        ),
    )


_MAX_VISION_PX = 1568  # OpenAI's internal tile limit — no benefit sending larger


def _prepare_image_b64(image_path: str) -> str:
    """
    Send the image as-is — no sharpening, no contrast, no re-encoding.
    gpt-5.4 reads the original file better than any preprocessed version.
    Only exception: EXIF auto-rotate (lossless, fixes sideways phone photos).
    """
    try:
        from PIL import Image, ImageOps
        import io
        with Image.open(image_path) as img:
            img = ImageOps.exif_transpose(img)
            # Only re-save if EXIF rotation actually changed the image
            if img != Image.open(image_path):
                buf = io.BytesIO()
                fmt = img.format or "JPEG"
                img.save(buf, format=fmt)
                return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        pass
    # Default: send raw bytes untouched
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _vision_call(client, img_b64: str, prompt: str) -> str:
    """
    Call the vision model with an image.
    Uses the Responses API (gpt-5.x) with fallback to Chat Completions API (gpt-4o).
    """
    try:
        resp = client.responses.create(
            model=config.OPENAI_MODEL,
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{img_b64}"},
                ],
            }],
        )
        return resp.output_text.strip()
    except AttributeError:
        # client.responses not available — older SDK, fall back to chat.completions
        resp = client.chat.completions.create(
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
        return resp.choices[0].message.content.strip()


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
        text = _vision_call(client, img_b64, prompt)
        items = _parse_json_response(text)
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
    Two-step extraction from a menu photo:
      1. Vision call (GPT-4o): read all visible text as faithfully as possible.
      2. Text-only call (GPT-4o-mini): parse that raw text into structured items.
    Separating OCR from parsing improves accuracy for both steps.
    """
    try:
        client = _get_client()
    except ImportError:
        return []

    # ── Step 1: OCR — read everything off the image ──────────────────────────
    img_b64 = _prepare_image_b64(image_path)
    ocr_prompt = (
        "Extract all text from this image exactly as it appears. "
        "Do not correct, interpret, or change any words. "
        "Preserve the layout — keep prices next to their items."
    )
    try:
        raw_text = _vision_call(client, img_b64, ocr_prompt)
        print(f"[AI] OCR extracted {len(raw_text)} chars from {os.path.basename(image_path)}")
    except Exception as e:
        print(f"[AI] OCR error for {os.path.basename(image_path)}: {e}")
        return []

    if not raw_text or len(raw_text) < 10:
        return []

    # ── Step 2: Parse — structure the raw text into menu items ───────────────
    parse_prompt = (
        "You are a restaurant menu parser. Below is raw OCR text from a restaurant menu.\n"
        "Parse it into a structured list of menu items. Return ONLY a valid JSON array:\n"
        '[{"name":"...","category":"...","subcategory":"...","ingredients":"...","price":"..."}]\n\n'
        "RULES:\n"
        "- name: the dish or drink name (required — skip if unclear)\n"
        "- category: the menu section this item belongs to (e.g. სალათები, ცხელი კერძები, სასმელი, Salads, Hot Dishes)\n"
        "- subcategory: sub-section if present, else empty string\n"
        "- ingredients: description or ingredients visible in the text, else empty string\n"
        "- price: numeric value only (e.g. '12.50'), empty string if not found\n"
        "- SKIP section headers, decorative text, restaurant name, address, phone numbers\n"
        "- SKIP entries where the name is a number, a price, or fewer than 2 characters\n"
        "- If a price appears on the same line or directly after an item name, assign it to that item\n"
        "Return [] if no valid items found.\n\n"
        "RAW MENU TEXT:\n" + raw_text
    )
    try:
        parse_resp = client.chat.completions.create(
            model=config.OPENAI_MODEL_MINI,
            messages=[{"role": "user", "content": parse_prompt}],
            max_tokens=4096,
        )
        items = _parse_json_response(parse_resp.choices[0].message.content)
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
        print(f"[AI] Parsed {len(filtered)} items from {os.path.basename(image_path)}")
        return filtered
    except Exception as e:
        print(f"[AI] Parse error for {os.path.basename(image_path)}: {e}")
        return []


def assign_global_categories(items: list, global_cats: list, global_subcats: list) -> list:
    """
    Map each item's extracted category/subcategory to the closest GlobalLibrary entry.

    global_cats   — list of {id, name} from GlobalCategory
    global_subcats — list of {id, name, category_id} from GlobalSubcategory

    Sets item['category_id'], item['category'] (canonical name),
         item['subcategory_id'], item['subcategory'] (canonical name).
    Items with no category get one assigned by GPT based on the dish name.
    """
    if not items:
        return items

    try:
        client = _get_client()
    except ImportError:
        return items

    cat_names = [c["name"] for c in global_cats]
    sub_names = [s["name"] for s in global_subcats]

    # Build lookup dicts: lower name → entry
    cat_by_name = {c["name"].lower(): c for c in global_cats}
    sub_by_name = {s["name"].lower(): s for s in global_subcats}

    # Collect unique extracted values
    unique_cats = list({it.get("category", "").strip() for it in items if it.get("category")})
    unique_subs = list({it.get("subcategory", "").strip() for it in items if it.get("subcategory")})
    items_no_cat = [it["name"] for it in items if not it.get("category")]

    cat_mapping = {}   # extracted_name_lower → GlobalCategory entry
    sub_mapping = {}   # extracted_name_lower → GlobalSubcategory entry

    # Step 1: map extracted categories → GlobalCategory
    if unique_cats or items_no_cat:
        to_map = unique_cats + items_no_cat
        prompt = (
            "You are a restaurant menu classifier. For each dish/category name below, "
            "pick the SINGLE closest matching category from the provided GlobalLibrary list.\n"
            "Return ONLY valid JSON: {\"input_name\": \"matched_global_category_name\"}.\n"
            "If nothing fits well, use the most general applicable category.\n\n"
            "GlobalLibrary categories:\n" + json.dumps(cat_names, ensure_ascii=False) + "\n\n"
            "Items to classify:\n" + json.dumps(to_map, ensure_ascii=False)
        )
        try:
            resp = client.chat.completions.create(
                model=config.OPENAI_MODEL_MINI,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            raw = _parse_json_response(resp.choices[0].message.content)
            for k, v in raw.items():
                matched = cat_by_name.get(v.lower())
                if matched:
                    cat_mapping[k.lower()] = matched
            print(f"[AI] Category mapping: {len(cat_mapping)} matched")
        except Exception as e:
            print(f"[AI] Category mapping error: {e}")

    # Step 2: map extracted subcategories → GlobalSubcategory
    if unique_subs:
        prompt = (
            "For each subcategory name below, pick the closest match from the GlobalLibrary subcategory list.\n"
            "Return ONLY valid JSON: {\"input_name\": \"matched_global_subcategory_name\"}.\n"
            "If nothing fits, use the closest. Never return empty.\n\n"
            "GlobalLibrary subcategories:\n" + json.dumps(sub_names, ensure_ascii=False) + "\n\n"
            "Subcategories to classify:\n" + json.dumps(unique_subs, ensure_ascii=False)
        )
        try:
            resp = client.chat.completions.create(
                model=config.OPENAI_MODEL_MINI,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            raw = _parse_json_response(resp.choices[0].message.content)
            for k, v in raw.items():
                matched = sub_by_name.get(v.lower())
                if matched:
                    sub_mapping[k.lower()] = matched
            print(f"[AI] Subcategory mapping: {len(sub_mapping)} matched")
        except Exception as e:
            print(f"[AI] Subcategory mapping error: {e}")

    # Step 3: Apply mappings to every item
    for it in items:
        raw_cat = it.get("category", "").strip()
        cat_entry = cat_mapping.get(raw_cat.lower()) or cat_mapping.get(it["name"].lower())
        if cat_entry:
            it["category"] = cat_entry["name"]
            it["category_id"] = cat_entry["id"]
        else:
            it.setdefault("category", raw_cat or "სხვა")
            it["category_id"] = None

        raw_sub = it.get("subcategory", "").strip()
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


def translate_items_bilingual(items: list) -> list:
    """
    For every item produce name_ka, name_en, ingredients_ka, ingredients_en.
    Detects source language per item and translates to the other.
    Uses culinary-domain restaurant menu vocabulary.
    Modifies items in-place and returns them.
    """
    if not items:
        return items
    try:
        client = _get_client()
    except ImportError:
        for it in items:
            it.setdefault("name_ka", it.get("name", ""))
            it.setdefault("name_en", it.get("name", ""))
            it.setdefault("ingredients_ka", it.get("ingredients", ""))
            it.setdefault("ingredients_en", "")
        return items

    BATCH = 40
    for i in range(0, len(items), BATCH):
        batch = items[i:i + BATCH]
        payload = [
            {
                "i": j,
                "name": it.get("name", ""),
                "category": it.get("category", ""),
                "ingredients": it.get("ingredients", ""),
            }
            for j, it in enumerate(batch)
        ]
        prompt = (
            "You are a professional restaurant menu translator specializing in Georgian and international cuisine.\n"
            "TASK: For each menu item provide BOTH Georgian (ka) and English (en) versions of the name, "
            "category, and ingredients.\n\n"
            "CRITICAL RULES:\n"
            "- This is a RESTAURANT MENU. Use precise culinary terminology as it appears on upscale menus — "
            "NOT generic dictionary translations.\n"
            "- For traditional Georgian dishes (ხინკალი, ლობიანი, მწვადი, ჩაქაფული, etc.): "
            "keep the authentic Georgian name in 'name_ka'; use the standard English culinary term or "
            "transliteration in 'name_en' (e.g. 'Khinkali', 'Lobiani', 'Mtsvadi').\n"
            "- For international dishes (pizza, pasta, steak, etc.): translate/transliterate into Georgian "
            "script for 'name_ka' using the accepted Georgian form.\n"
            "- 'category_en': translate the category name to English (e.g. სალათები→Salads, ცხელი კერძები→Main Courses).\n"
            "- Ingredients: comma-separated list of 3-6 typical ingredients in the target language. "
            "If the input has ingredients, translate them accurately. If empty, generate typical ingredients "
            "for that dish using culinary knowledge.\n"
            "- For drinks: ingredients_ka and ingredients_en should be empty strings.\n"
            "- Detect whether each input name is Georgian or English and translate to the OTHER language.\n\n"
            "Return ONLY valid JSON array (SAME ORDER and COUNT as input):\n"
            '[{"i":0,"name_ka":"ქართული სახელი","name_en":"English Name","category_en":"Category",'
            '"ingredients_ka":"ინგ1, ინგ2, ინგ3","ingredients_en":"ing1, ing2, ing3"}]\n\n'
            "Items:\n" + json.dumps(payload, ensure_ascii=False)
        )
        try:
            response = client.chat.completions.create(
                model=config.OPENAI_MODEL_MINI,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
            results = _parse_json_response(response.choices[0].message.content)
            result_map = {r["i"]: r for r in results if isinstance(r, dict)}
            for j, it in enumerate(batch):
                r = result_map.get(j, {})
                it["name_ka"] = (r.get("name_ka") or it.get("name", "")).strip()
                it["name_en"] = (r.get("name_en") or it.get("name", "")).strip()
                it["category_en"] = (r.get("category_en") or it.get("category", "")).strip()
                it["ingredients_ka"] = (r.get("ingredients_ka") or it.get("ingredients", "")).strip()
                it["ingredients_en"] = (r.get("ingredients_en") or "").strip()
        except Exception as e:
            print(f"[AI] translate_items_bilingual error: {e}")
            for it in batch:
                it.setdefault("name_ka", it.get("name", ""))
                it.setdefault("name_en", it.get("name", ""))
                it.setdefault("category_en", it.get("category", ""))
                it.setdefault("ingredients_ka", it.get("ingredients", ""))
                it.setdefault("ingredients_en", "")

    print(f"[AI] Bilingual translation done for {len(items)} items")
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
