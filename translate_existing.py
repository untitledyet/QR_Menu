# -*- coding: utf-8 -*-
"""
Bulk-translate existing GlobalCategory, GlobalSubcategory, GlobalItem records.
Runs against whichever DB is in .env (Railway by default).

Usage:
    source venv/bin/activate
    python translate_existing.py           # translate KA→EN for empty _en fields
    python translate_existing.py --fix-ka  # translate EN→KA for records whose KA field is English

Only records with empty _en fields are translated (default mode). Safe to re-run.
--fix-ka mode: detects records where KA field looks like English and translates to Georgian.
"""
import sys
import time
from app import create_app, db
from app.services.translation_service import _call_openai as _call_gemini
import os

app = create_app()
API_KEY = os.environ.get('OPENAI_API_KEY', '')
DELAY = 1.5  # seconds between OpenAI calls to avoid rate limits

FIX_KA_MODE = '--fix-ka' in sys.argv


def _looks_english(text):
    """Return True if text contains mostly ASCII characters (i.e. likely English, not Georgian)."""
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return ascii_count / len(text) > 0.8


def translate_fields(fields, source_lang, target_lang, label):
    """Call OpenAI and return result dict, or None on failure."""
    try:
        result = _call_gemini(fields, source_lang, target_lang, API_KEY)
        print(f'  ✓  {label}')
        return result
    except Exception as e:
        print(f'  ✗  {label} — {e}')
        return None


def run_ka_to_en():
    """Translate KA→EN for records that have empty _en fields."""
    with app.app_context():
        from app.models import GlobalCategory, GlobalSubcategory, GlobalItem, Category, Subcategory, FoodItem

        # ── 1. GlobalCategory ──────────────────────────────────────────────
        cats = GlobalCategory.query.filter(
            (GlobalCategory.name_en == None) | (GlobalCategory.name_en == '')
        ).all()
        print(f'\n[GlobalCategory] {len(cats)} untranslated records\n')

        for cat in cats:
            fields = {'name': cat.name, 'description': cat.description or ''}
            result = translate_fields(fields, 'ka', 'en', f'Category: {cat.name}')
            if result:
                cat.name_en = result.get('name') or cat.name_en
                cat.description_en = result.get('description') or cat.description_en
                db.session.commit()
            time.sleep(DELAY)

        # ── 2. GlobalSubcategory ───────────────────────────────────────────
        subs = GlobalSubcategory.query.filter(
            (GlobalSubcategory.name_en == None) | (GlobalSubcategory.name_en == '')
        ).all()
        print(f'\n[GlobalSubcategory] {len(subs)} untranslated records\n')

        for sub in subs:
            fields = {'name': sub.name, 'description': ''}
            result = translate_fields(fields, 'ka', 'en', f'Subcategory: {sub.name}')
            if result:
                sub.name_en = result.get('name') or sub.name_en
                db.session.commit()
            time.sleep(DELAY)

        # ── 3. GlobalItem ──────────────────────────────────────────────────
        items = GlobalItem.query.filter(
            (GlobalItem.name_en == None) | (GlobalItem.name_en == '')
        ).all()
        print(f'\n[GlobalItem] {len(items)} untranslated records\n')

        for item in items:
            fields = {
                'name': item.name,
                'description': item.description or '',
                'ingredients': item.ingredients or '',
            }
            result = translate_fields(fields, 'ka', 'en', f'Item: {item.name}')
            if result:
                item.name_en = result.get('name') or item.name_en
                item.description_en = result.get('description') or item.description_en
                item.ingredients_en = result.get('ingredients') or item.ingredients_en
                db.session.commit()
            time.sleep(DELAY)

        # ── 4. Venue Category ─────────────────────────────────────────────
        vcats = Category.query.filter(
            (Category.CategoryName_en == None) | (Category.CategoryName_en == '')
        ).all()
        print(f'\n[Venue Category] {len(vcats)} untranslated records\n')

        for cat in vcats:
            fields = {'name': cat.CategoryName, 'description': cat.Description or ''}
            result = translate_fields(fields, 'ka', 'en', f'VenueCategory: {cat.CategoryName}')
            if result:
                cat.CategoryName_en = result.get('name') or cat.CategoryName_en
                cat.Description_en = result.get('description') or cat.Description_en
                db.session.commit()
            time.sleep(DELAY)

        # ── 5. Venue Subcategory ───────────────────────────────────────────
        vsubs = Subcategory.query.filter(
            (Subcategory.SubcategoryName_en == None) | (Subcategory.SubcategoryName_en == '')
        ).all()
        print(f'\n[Venue Subcategory] {len(vsubs)} untranslated records\n')

        for sub in vsubs:
            fields = {'name': sub.SubcategoryName, 'description': ''}
            result = translate_fields(fields, 'ka', 'en', f'VenueSub: {sub.SubcategoryName}')
            if result:
                sub.SubcategoryName_en = result.get('name') or sub.SubcategoryName_en
                db.session.commit()
            time.sleep(DELAY)

        # ── 6. Venue FoodItem ──────────────────────────────────────────────
        vitems = FoodItem.query.filter(
            (FoodItem.FoodName_en == None) | (FoodItem.FoodName_en == '')
        ).all()
        print(f'\n[Venue FoodItem] {len(vitems)} untranslated records\n')

        for item in vitems:
            fields = {
                'name': item.FoodName,
                'description': item.Description or '',
                'ingredients': item.Ingredients or '',
            }
            result = translate_fields(fields, 'ka', 'en', f'FoodItem: {item.FoodName}')
            if result:
                item.FoodName_en = result.get('name') or item.FoodName_en
                item.Description_en = result.get('description') or item.Description_en
                item.Ingredients_en = result.get('ingredients') or item.Ingredients_en
                db.session.commit()
            time.sleep(DELAY)

        print('\nDone.')


def run_fix_ka():
    """
    For records where the primary (KA) field looks like English,
    translate EN→KA and overwrite the KA field.
    Also ensures _en field has the English original.
    """
    with app.app_context():
        from app.models import GlobalCategory, GlobalSubcategory, GlobalItem, Category, Subcategory, FoodItem

        # ── 1. GlobalCategory ──────────────────────────────────────────────
        cats = GlobalCategory.query.all()
        to_fix = [c for c in cats if _looks_english(c.name)]
        print(f'\n[GlobalCategory --fix-ka] {len(to_fix)} records with English in KA field\n')

        for cat in to_fix:
            # Preserve English into _en if not already set
            if not cat.name_en:
                cat.name_en = cat.name
            if not cat.description_en and cat.description:
                cat.description_en = cat.description

            fields = {'name': cat.name_en, 'description': cat.description_en or ''}
            result = translate_fields(fields, 'en', 'ka', f'Category: {cat.name}')
            if result:
                cat.name = result.get('name') or cat.name
                cat.description = result.get('description') or cat.description
                db.session.commit()
            time.sleep(DELAY)

        # ── 2. GlobalSubcategory ───────────────────────────────────────────
        subs = GlobalSubcategory.query.all()
        to_fix = [s for s in subs if _looks_english(s.name)]
        print(f'\n[GlobalSubcategory --fix-ka] {len(to_fix)} records with English in KA field\n')

        for sub in to_fix:
            if not sub.name_en:
                sub.name_en = sub.name
            fields = {'name': sub.name_en, 'description': ''}
            result = translate_fields(fields, 'en', 'ka', f'Subcategory: {sub.name}')
            if result:
                sub.name = result.get('name') or sub.name
                db.session.commit()
            time.sleep(DELAY)

        # ── 3. GlobalItem ──────────────────────────────────────────────────
        items = GlobalItem.query.all()
        to_fix = [i for i in items if _looks_english(i.name)]
        print(f'\n[GlobalItem --fix-ka] {len(to_fix)} records with English in KA field\n')

        for item in to_fix:
            if not item.name_en:
                item.name_en = item.name
            if not item.description_en and item.description:
                item.description_en = item.description
            if not item.ingredients_en and item.ingredients:
                item.ingredients_en = item.ingredients

            fields = {
                'name': item.name_en,
                'description': item.description_en or '',
                'ingredients': item.ingredients_en or '',
            }
            result = translate_fields(fields, 'en', 'ka', f'Item: {item.name}')
            if result:
                item.name = result.get('name') or item.name
                item.description = result.get('description') or item.description
                item.ingredients = result.get('ingredients') or item.ingredients
                db.session.commit()
            time.sleep(DELAY)

        # ── 4. Venue Category ─────────────────────────────────────────────
        vcats = Category.query.all()
        to_fix = [c for c in vcats if _looks_english(c.CategoryName)]
        print(f'\n[Venue Category --fix-ka] {len(to_fix)} records with English in KA field\n')

        for cat in to_fix:
            if not cat.CategoryName_en:
                cat.CategoryName_en = cat.CategoryName
            if not cat.Description_en and cat.Description:
                cat.Description_en = cat.Description

            fields = {'name': cat.CategoryName_en, 'description': cat.Description_en or ''}
            result = translate_fields(fields, 'en', 'ka', f'VenueCategory: {cat.CategoryName}')
            if result:
                cat.CategoryName = result.get('name') or cat.CategoryName
                cat.Description = result.get('description') or cat.Description
                db.session.commit()
            time.sleep(DELAY)

        # ── 5. Venue Subcategory ───────────────────────────────────────────
        vsubs = Subcategory.query.all()
        to_fix = [s for s in vsubs if _looks_english(s.SubcategoryName)]
        print(f'\n[Venue Subcategory --fix-ka] {len(to_fix)} records with English in KA field\n')

        for sub in to_fix:
            if not sub.SubcategoryName_en:
                sub.SubcategoryName_en = sub.SubcategoryName
            fields = {'name': sub.SubcategoryName_en, 'description': ''}
            result = translate_fields(fields, 'en', 'ka', f'VenueSub: {sub.SubcategoryName}')
            if result:
                sub.SubcategoryName = result.get('name') or sub.SubcategoryName
                db.session.commit()
            time.sleep(DELAY)

        # ── 6. Venue FoodItem ──────────────────────────────────────────────
        vitems = FoodItem.query.all()
        to_fix = [i for i in vitems if _looks_english(i.FoodName)]
        print(f'\n[Venue FoodItem --fix-ka] {len(to_fix)} records with English in KA field\n')

        for item in to_fix:
            if not item.FoodName_en:
                item.FoodName_en = item.FoodName
            if not item.Description_en and item.Description:
                item.Description_en = item.Description
            if not item.Ingredients_en and item.Ingredients:
                item.Ingredients_en = item.Ingredients

            fields = {
                'name': item.FoodName_en,
                'description': item.Description_en or '',
                'ingredients': item.Ingredients_en or '',
            }
            result = translate_fields(fields, 'en', 'ka', f'FoodItem: {item.FoodName}')
            if result:
                item.FoodName = result.get('name') or item.FoodName
                item.Description = result.get('description') or item.Description
                item.Ingredients = result.get('ingredients') or item.Ingredients
                db.session.commit()
            time.sleep(DELAY)

        print('\nDone.')


if __name__ == '__main__':
    if not API_KEY:
        print('ERROR: OPENAI_API_KEY not set in .env')
        sys.exit(1)

    if FIX_KA_MODE:
        print('Mode: --fix-ka (translate English KA fields → Georgian)')
        run_fix_ka()
    else:
        print('Mode: KA→EN (fill missing _en fields)')
        run_ka_to_en()
