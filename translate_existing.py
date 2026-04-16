# -*- coding: utf-8 -*-
"""
Bulk-translate existing GlobalCategory, GlobalSubcategory, GlobalItem records.
Runs against whichever DB is in .env (Railway by default).

Usage:
    source venv/bin/activate
    python translate_existing.py

Only records with empty _en fields are translated. Safe to re-run.
"""
import time
from app import create_app, db
from app.services.translation_service import _call_gemini
import os

app = create_app()
API_KEY = os.environ.get('OPENAI_API_KEY', '')
DELAY = 1.5  # seconds between Gemini calls to avoid rate limits


def translate_fields(fields, source_lang, target_lang, label):
    """Call Gemini and return result dict, or None on failure."""
    try:
        result = _call_gemini(fields, source_lang, target_lang, API_KEY)
        print(f'  ✓  {label}')
        return result
    except Exception as e:
        print(f'  ✗  {label} — {e}')
        return None


def run():
    if not API_KEY:
        print('ERROR: OPENAI_API_KEY not set in .env')
        return

    with app.app_context():
        from app.models import GlobalCategory, GlobalSubcategory, GlobalItem

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

        print('\nDone.')


if __name__ == '__main__':
    run()
