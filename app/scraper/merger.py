"""
Merger — combines data from all sources into a complete menu.

Priority rules:
  Prices:       google_text > google_photos_ai  (Glovo prices NEVER used)
  Categories:   google_text > glovo > photos_ai > AI categorization
  Items:        google_text > glovo > photos_ai
  Descriptions: google_text > glovo > photos_ai > AI enrichment
  Photos:       glovo images > AI web search
"""
import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_price(price_str: str) -> str:
    """Extract numeric price from various string formats."""
    if not price_str:
        return ""
    m = re.search(r"\d+[,.]\d+", price_str.replace(" ", ""))
    if m:
        return m.group(0).replace(",", ".")
    # integer price (e.g. "15")
    m2 = re.search(r"\d+", price_str)
    if m2:
        return m2.group(0) + ".00"
    return ""


def _key(name: str) -> str:
    """Normalised lookup key for deduplication."""
    return name.lower().strip()


# ---------------------------------------------------------------------------
# Main merge function
# ---------------------------------------------------------------------------

def merge_menu(google_text, google_photos_ai, glovo_data, glovo_photo_map):
    """
    Merge all sources into final menu dict.

    Parameters
    ----------
    google_text       : dict {cat: [{name, description, price}]} or None
    google_photos_ai  : dict {cat: [{name, description, price, category}]} or None
    glovo_data        : dict {cat: [{name, description, image}]} or None
                        NOTE: Glovo prices are intentionally ignored.
    glovo_photo_map   : dict {name_lower: local_image_path}

    Returns
    -------
    dict {category: [{name, description, price, image, source}]}
    """

    # ------------------------------------------------------------------ #
    # CASE 1 — Google text menu available                                 #
    # ------------------------------------------------------------------ #
    if google_text:
        final = {}

        # 1a. Seed from Google text (highest priority)
        for cat, items in google_text.items():
            final[cat] = []
            for it in items:
                final[cat].append({
                    "name": it.get("name", ""),
                    "description": it.get("description", ""),
                    "price": normalize_price(it.get("price", "")),
                    "image": "",
                    "source": "google_text",
                })

        # 1b. Merge Google photo-AI items (fill missing prices / descriptions,
        #     and add items that exist in photos but not in text menu)
        if google_photos_ai:
            print("[Merger] Merging Google photo-AI data into text menu")
            # flat lookup: name_key -> item in final
            final_flat = {}
            for cat in final:
                for it in final[cat]:
                    final_flat[_key(it["name"])] = it

            for cat, items in google_photos_ai.items():
                for ai_it in items:
                    k = _key(ai_it.get("name", ""))
                    if not k:
                        continue
                    if k in final_flat:
                        existing = final_flat[k]
                        # Fill missing price (prefer higher price)
                        ai_price = normalize_price(ai_it.get("price", ""))
                        if ai_price:
                            if not existing["price"]:
                                existing["price"] = ai_price
                                existing["source"] += "+photo_ai_price"
                            else:
                                # Keep the higher price
                                try:
                                    if float(ai_price) > float(existing["price"]):
                                        existing["price"] = ai_price
                                        existing["source"] += "+photo_ai_price_higher"
                                except ValueError:
                                    pass
                        # Fill missing description
                        if not existing["description"] and ai_it.get("description"):
                            existing["description"] = ai_it["description"]
                            existing["source"] += "+photo_ai_desc"
                    else:
                        # Item exists in photo but not in text menu — add it
                        target_cat = ai_it.get("category") or cat
                        if target_cat not in final:
                            final[target_cat] = []
                        final[target_cat].append({
                            "name": ai_it.get("name", ""),
                            "description": ai_it.get("description", ""),
                            "price": normalize_price(ai_it.get("price", "")),
                            "image": "",
                            "source": "photo_ai",
                        })
                        final_flat[k] = final[target_cat][-1]

        # 1c. Attach Glovo photos (no prices from Glovo)
        if glovo_data or glovo_photo_map:
            print("[Merger] Attaching Glovo photos to items")
            # Build name->image from glovo_data (remote URLs) as fallback
            glovo_remote = {}
            if glovo_data:
                for cat, items in glovo_data.items():
                    for it in items:
                        k = _key(it.get("name", ""))
                        if k and it.get("image"):
                            glovo_remote[k] = it["image"]

            for cat in final:
                for item in final[cat]:
                    k = _key(item["name"])
                    if glovo_photo_map.get(k):
                        item["image"] = glovo_photo_map[k]
                    elif glovo_remote.get(k):
                        item["image"] = glovo_remote[k]

        _dedup_final(final)
        _print_stats(final)
        return final

    # ------------------------------------------------------------------ #
    # CASE 2 — No Google text, but Glovo + photo menu available           #
    # ------------------------------------------------------------------ #
    if glovo_data and google_photos_ai:
        print("[Merger] No Google text — using Glovo + photo-AI")
        final = {}

        # Seed from Glovo (NO prices)
        for cat, items in glovo_data.items():
            final[cat] = []
            for it in items:
                final[cat].append({
                    "name": it.get("name", ""),
                    "description": it.get("description", ""),
                    "price": "",          # Glovo prices intentionally excluded
                    "image": it.get("image", ""),
                    "source": "glovo",
                })

        # Overlay local Glovo photos
        if glovo_photo_map:
            for cat in final:
                for item in final[cat]:
                    k = _key(item["name"])
                    if glovo_photo_map.get(k):
                        item["image"] = glovo_photo_map[k]

        # Merge photo-AI: fill prices + descriptions, add missing items
        final_flat = {}
        for cat in final:
            for it in final[cat]:
                final_flat[_key(it["name"])] = it

        for cat, items in google_photos_ai.items():
            for ai_it in items:
                k = _key(ai_it.get("name", ""))
                if not k:
                    continue
                ai_price = normalize_price(ai_it.get("price", ""))
                if k in final_flat:
                    existing = final_flat[k]
                    # Prices come ONLY from photo-AI here
                    if ai_price and not existing["price"]:
                        existing["price"] = ai_price
                        existing["source"] += "+photo_ai_price"
                    if not existing["description"] and ai_it.get("description"):
                        existing["description"] = ai_it["description"]
                else:
                    target_cat = ai_it.get("category") or cat
                    if target_cat not in final:
                        final[target_cat] = []
                    final[target_cat].append({
                        "name": ai_it.get("name", ""),
                        "description": ai_it.get("description", ""),
                        "price": ai_price,
                        "image": "",
                        "source": "photo_ai",
                    })
                    final_flat[k] = final[target_cat][-1]

        _dedup_final(final)
        _print_stats(final)
        return final

    # ------------------------------------------------------------------ #
    # CASE 3 — Only Glovo available                                       #
    # ------------------------------------------------------------------ #
    if glovo_data:
        print("[Merger] Only Glovo available (no prices)")
        final = {}
        for cat, items in glovo_data.items():
            final[cat] = []
            for it in items:
                final[cat].append({
                    "name": it.get("name", ""),
                    "description": it.get("description", ""),
                    "price": "",
                    "image": it.get("image", ""),
                    "source": "glovo",
                })
        if glovo_photo_map:
            for cat in final:
                for item in final[cat]:
                    k = _key(item["name"])
                    if glovo_photo_map.get(k):
                        item["image"] = glovo_photo_map[k]
        _dedup_final(final)
        _print_stats(final)
        return final

    # ------------------------------------------------------------------ #
    # CASE 4 — Only photo-AI available                                    #
    # ------------------------------------------------------------------ #
    if google_photos_ai:
        print("[Merger] Only photo-AI available")
        final = {}
        for cat, items in google_photos_ai.items():
            final[cat] = []
            for it in items:
                final[cat].append({
                    "name": it.get("name", ""),
                    "description": it.get("description", ""),
                    "price": normalize_price(it.get("price", "")),
                    "image": "",
                    "source": "photo_ai",
                })
        _dedup_final(final)
        _print_stats(final)
        return final

    print("[Merger] No data from any source")
    return {}


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _dedup_final(final: dict):
    """
    Remove duplicate items across all categories.
    If same item appears with different prices, keep the higher price.
    Modifies `final` in-place.
    """
    seen = {}  # name_key -> (cat, index)

    for cat in list(final.keys()):
        kept = []
        for item in final[cat]:
            k = _key(item["name"])
            if not k:
                kept.append(item)
                continue
            if k not in seen:
                seen[k] = item
                kept.append(item)
            else:
                existing = seen[k]
                # Keep higher price
                try:
                    new_p = float(item.get("price") or 0)
                    old_p = float(existing.get("price") or 0)
                    if new_p > old_p:
                        existing["price"] = item["price"]
                except ValueError:
                    pass
                # Fill missing fields from duplicate
                if not existing.get("description") and item.get("description"):
                    existing["description"] = item["description"]
                if not existing.get("image") and item.get("image"):
                    existing["image"] = item["image"]
                # Skip adding duplicate
        final[cat] = kept

    # Remove empty categories
    for cat in list(final.keys()):
        if not final[cat]:
            del final[cat]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _print_stats(final: dict):
    total = sum(len(v) for v in final.values())
    with_price = sum(1 for cat in final for it in final[cat] if it.get("price"))
    with_desc = sum(1 for cat in final for it in final[cat] if it.get("description"))
    with_img = sum(1 for cat in final for it in final[cat] if it.get("image"))
    print(
        f"[Merger] Final: {total} items | "
        f"{with_price} with price | "
        f"{with_desc} with description | "
        f"{with_img} with image"
    )
