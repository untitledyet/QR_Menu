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
    Use GPT-4o-mini to add standard ingredients for items missing descriptions.
    Modifies items in-place and returns them.
    """
    missing = [it for it in items if not it.get("description")]
    if not missing:
        return items

    try:
        client = _get_client()
    except ImportError:
        return items

    names = [it["name"] for it in missing]
    prompt = (
        "For each Georgian dish, provide typical ingredients in Georgian language. "
        "Return ONLY valid JSON object: {\"dish_name\": \"ingredients\"}.\n"
        "Dishes: " + json.dumps(names, ensure_ascii=False)
    )

    try:
        response = client.chat.completions.create(
            model=config.OPENAI_MODEL_MINI,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        ingredients_map = _parse_json_response(response.choices[0].message.content)
        for it in items:
            if not it.get("description") and it["name"] in ingredients_map:
                it["description"] = ingredients_map[it["name"]]
        print("[AI] Enriched " + str(len(ingredients_map)) + " items with ingredients")
    except Exception as e:
        print("[AI] Enrichment error: " + str(e))

    return items


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
