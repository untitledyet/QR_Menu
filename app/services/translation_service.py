"""
Auto-translation service using Gemini AI.
Translates restaurant menu content (items, categories) between Georgian and English.
Runs asynchronously — saves to DB after item is already committed.
"""
import os
import re
import json
import threading


GEMINI_MODEL = 'gemini-2.5-flash'

# Professional culinary translation prompt
_PROMPT_TEMPLATE = """\
You are a professional culinary translator specialising in restaurant menus and gastronomy.
Translate the JSON content below from {source} to {target}.

Rules:
- Use accurate, professional culinary and gastronomic terminology.
- Ingredient names must be precise (e.g. "beef tenderloin", "extra-virgin olive oil").
- Category names must be concise and standard for restaurant menus.
- Preserve any empty string as an empty string.
- Return ONLY a valid JSON object with the exact same keys as the input. No markdown, no explanation.

Input JSON:
{content}"""


def _call_gemini(fields: dict, source_lang: str, target_lang: str, api_key: str) -> dict:
    """Call Gemini REST API and return translated dict. Raises on failure."""
    import requests
    try:
        import certifi
        verify = certifi.where()
    except ImportError:
        verify = True

    src = 'Georgian' if source_lang == 'ka' else 'English'
    tgt = 'Georgian' if target_lang == 'ka' else 'English'
    content = json.dumps(fields, ensure_ascii=False)
    prompt = _PROMPT_TEMPLATE.format(source=src, target=tgt, content=content)

    url = (
        'https://generativelanguage.googleapis.com/v1beta/models/'
        f'{GEMINI_MODEL}:generateContent?key={api_key}'
    )
    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 1024},
    }
    resp = requests.post(url, json=payload, verify=verify, timeout=20)
    resp.raise_for_status()

    text = resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()

    # Extract JSON object from response (handles markdown code blocks)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError('No JSON object found in Gemini response')

    return json.loads(match.group(0))


def translate_item_async(item_id: int, fields: dict, source_lang: str, target_lang: str, app):
    """
    Translate FoodItem fields in background and update DB.

    fields: dict with keys 'name', 'description', 'ingredients'
    source_lang / target_lang: 'ka' or 'en'
    """
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        return

    def _run():
        try:
            result = _call_gemini(fields, source_lang, target_lang, api_key)
        except Exception as exc:
            try:
                app.logger.error('[TRANSLATE] Gemini error for item %s: %s', item_id, exc)
            except Exception:
                pass
            return

        try:
            with app.app_context():
                from app import db
                from app.models import FoodItem
                item = FoodItem.query.get(item_id)
                if not item:
                    return
                if target_lang == 'en':
                    item.FoodName_en = result.get('name') or item.FoodName_en
                    item.Description_en = result.get('description') or item.Description_en
                    item.Ingredients_en = result.get('ingredients') or item.Ingredients_en
                else:
                    item.FoodName = result.get('name') or item.FoodName
                    item.Description = result.get('description') or item.Description
                    item.Ingredients = result.get('ingredients') or item.Ingredients
                db.session.commit()
                app.logger.info('[TRANSLATE] Item %s → %s done', item_id, target_lang)
        except Exception as exc:
            try:
                app.logger.error('[TRANSLATE] DB update failed for item %s: %s', item_id, exc)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()


def translate_category_async(cat_id: int, fields: dict, source_lang: str, target_lang: str, app):
    """
    Translate Category name/description in background and update DB.

    fields: dict with keys 'name', 'description'
    """
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        return

    def _run():
        try:
            result = _call_gemini(fields, source_lang, target_lang, api_key)
        except Exception as exc:
            try:
                app.logger.error('[TRANSLATE] Gemini error for category %s: %s', cat_id, exc)
            except Exception:
                pass
            return

        try:
            with app.app_context():
                from app import db
                from app.models import Category
                cat = Category.query.get(cat_id)
                if not cat:
                    return
                if target_lang == 'en':
                    cat.CategoryName_en = result.get('name') or cat.CategoryName_en
                    cat.Description_en = result.get('description') or cat.Description_en
                else:
                    cat.CategoryName = result.get('name') or cat.CategoryName
                    cat.Description = result.get('description') or cat.Description
                db.session.commit()
                app.logger.info('[TRANSLATE] Category %s → %s done', cat_id, target_lang)
        except Exception as exc:
            try:
                app.logger.error('[TRANSLATE] DB update failed for category %s: %s', cat_id, exc)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()


def translate_global_item_async(item_id: int, fields: dict, source_lang: str, target_lang: str, app):
    """Translate GlobalItem fields in background and update DB."""
    api_key = os.environ.get('GEMINI_API_KEY', '')
    if not api_key:
        return

    def _run():
        try:
            result = _call_gemini(fields, source_lang, target_lang, api_key)
        except Exception as exc:
            try:
                app.logger.error('[TRANSLATE] Gemini error for GlobalItem %s: %s', item_id, exc)
            except Exception:
                pass
            return

        try:
            with app.app_context():
                from app import db
                from app.models import GlobalItem
                item = GlobalItem.query.get(item_id)
                if not item:
                    return
                if target_lang == 'en':
                    item.name_en = result.get('name') or item.name_en
                    item.description_en = result.get('description') or item.description_en
                    item.ingredients_en = result.get('ingredients') or item.ingredients_en
                else:
                    item.name = result.get('name') or item.name
                    item.description = result.get('description') or item.description
                    item.ingredients = result.get('ingredients') or item.ingredients
                db.session.commit()
                app.logger.info('[TRANSLATE] GlobalItem %s → %s done', item_id, target_lang)
        except Exception as exc:
            try:
                app.logger.error('[TRANSLATE] DB update failed for GlobalItem %s: %s', item_id, exc)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()


def needs_translation(primary_val: str, secondary_val: str) -> bool:
    """True if primary is filled but secondary is empty — translation needed."""
    return bool(primary_val and primary_val.strip()) and not bool(secondary_val and secondary_val.strip())
