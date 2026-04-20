"""
Menu Extractor — Orchestrator
Extracts complete restaurant menu from Google Maps + Glovo + AI.

Usage: python -m scraper.extract_menu <google_maps_place_url>

Logic:
  1. Google text menu  — prices, categories, items, descriptions (highest priority)
  2. Google menu photos — AI extracts prices/items/descriptions from photos
  3. Glovo             — photos only (prices from Glovo are NEVER used)
  4. AI enrichment     — fill missing descriptions, categorize, find photos
"""
import sys
import os
import json

# ---------------------------------------------------------------------------
# Path setup — works both as `python -m scraper.extract_menu` and directly
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from google_menu import extract_google_text_menu
from google_photos import extract_google_menu_photos
from glovo_menu import find_glovo_url, extract_glovo_menu
from ai_analyzer import (
    analyze_menu_photo,
    categorize_items,
    enrich_ingredients,
)
from merger import merge_menu
from saver import save_menu_json, save_glovo_photos, save_google_photos


def main(place_url: str):
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    os.makedirs(config.PHOTOS_DIR, exist_ok=True)

    print("=" * 60)
    print("MENU EXTRACTOR")
    print("URL: " + place_url)
    print("=" * 60)

    google_text = None
    google_photo_urls = []   # raw base URLs from Google
    google_photos_ai = None  # AI-extracted data from downloaded photos
    glovo_data = None
    glovo_photo_map = {}     # {name_lower: local_path}

    # ======================================================================
    # BROWSER PHASE
    # ======================================================================
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config.HEADLESS, slow_mo=config.SLOW_MO)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        # ---- STEP 1: Google Text Menu ------------------------------------
        _header("STEP 1: Google Text Menu")
        try:
            google_text = extract_google_text_menu(page, place_url)
        except Exception as e:
            print("[GoogleMenu] Error: " + str(e))

        # ---- STEP 2: Google Menu Photos ----------------------------------
        _header("STEP 2: Google Menu Photos")
        try:
            # extract_google_menu_photos now returns base URLs (not downloaded)
            google_photo_urls = extract_google_menu_photos(page, place_url, config.PHOTOS_DIR)
        except Exception as e:
            print("[GooglePhotos] Error: " + str(e))

        # ---- STEP 3: Glovo -----------------------------------------------
        _header("STEP 3: Glovo Menu")
        try:
            glovo_url = find_glovo_url(page, place_url)
            if glovo_url:
                glovo_page = ctx.new_page()
                glovo_data = extract_glovo_menu(glovo_page, glovo_url)
                glovo_page.close()
        except Exception as e:
            print("[Glovo] Error: " + str(e))

        browser.close()

    # ======================================================================
    # SAVE PHASE — download photos locally
    # ======================================================================
    _header("STEP 4: Saving Photos")

    # Download Glovo item photos
    if glovo_data:
        glovo_photo_map = save_glovo_photos(glovo_data, config.PHOTOS_DIR)

    # Download Google menu photos
    local_photo_paths = []
    if google_photo_urls:
        local_photo_paths = save_google_photos(google_photo_urls, config.PHOTOS_DIR)

    # ======================================================================
    # AI ANALYSIS PHASE
    # ======================================================================
    _header("STEP 5: AI Photo Analysis")

    if local_photo_paths:
        all_ai_items = []
        for path in local_photo_paths:
            items = analyze_menu_photo(path)
            all_ai_items.extend(items)

        if all_ai_items:
            # Group by category field if present
            has_cats = any(it.get("category") for it in all_ai_items)
            if has_cats:
                google_photos_ai = {}
                for it in all_ai_items:
                    cat = it.get("category") or "Menu"
                    google_photos_ai.setdefault(cat, []).append(it)
            else:
                google_photos_ai = categorize_items(all_ai_items)
            print("[AI] Total extracted from photos: " + str(len(all_ai_items)) + " items")
    else:
        print("[AI] No Google menu photos to analyze")

    # ======================================================================
    # MERGE PHASE
    # ======================================================================
    _header("STEP 6: Merging All Sources")
    final_menu = merge_menu(google_text, google_photos_ai, glovo_data, glovo_photo_map)

    # ======================================================================
    # ENRICHMENT PHASE
    # ======================================================================
    _header("STEP 7: AI Enrichment")

    all_items = [it for items in final_menu.values() for it in items]

    # 7a. Fill missing descriptions
    missing_desc = sum(1 for it in all_items if not it.get("description"))
    if missing_desc > 0:
        print("[AI] " + str(missing_desc) + " items missing descriptions — enriching...")
        enrich_ingredients(all_items)
    else:
        print("[AI] All items have descriptions")

    # 7b. Auto-categorize if only 1 category with many items
    if len(final_menu) <= 1 and len(all_items) > 5:
        print("[AI] Only 1 category — auto-categorizing...")
        final_menu = categorize_items(all_items)
        all_items = [it for items in final_menu.values() for it in items]

    # 7c. Photos come only from Glovo — no generation needed

    # ======================================================================
    # SAVE FINAL OUTPUT
    # ======================================================================
    _header("STEP 8: Saving Output")
    save_menu_json(final_menu, config.OUTPUT_DIR)

    # ======================================================================
    # SUMMARY
    # ======================================================================
    print("\n" + "=" * 60)
    print("FINAL MENU SUMMARY")
    print("=" * 60)
    total = 0
    for cat, items in final_menu.items():
        print("\n[" + cat + "] — " + str(len(items)) + " items")
        for item in items:
            line = "  • " + item.get("name", "?")
            if item.get("price"):
                line += "  |  " + item["price"] + " GEL"
            if item.get("description"):
                d = item["description"]
                if isinstance(d, list):
                    d = ", ".join(str(x) for x in d)
                line += "  |  " + (d[:60] + "..." if len(d) > 60 else d)
            if item.get("image"):
                line += "  [IMG]"
            print(line)
        total += len(items)

    print("\n" + "=" * 60)
    print("DONE: " + str(total) + " items  →  " + os.path.join(config.OUTPUT_DIR, "menu_output.json"))
    print("=" * 60)


def _header(title: str):
    print("\n" + "=" * 40)
    print(title)
    print("=" * 40)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scraper.extract_menu <google_maps_place_url>")
        sys.exit(1)
    main(sys.argv[1])
