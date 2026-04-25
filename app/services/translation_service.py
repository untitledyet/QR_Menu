"""
Auto-translation service using OpenAI.
Translates restaurant menu content (items, categories) between Georgian and English.
Runs asynchronously — saves to DB after item is already committed.
"""
import os
import re
import json
import threading


OPENAI_MODEL = 'gpt-4o'

_SYSTEM_GE_TO_EN = (
    'You are a professional translator specializing in Georgian cuisine and gastronomy. '
    'Translate Georgian restaurant menu content into precise, natural English. '
    'For dish names: translate into natural English culinary terms (e.g. "ორაგულის სტეიკი" → "Salmon Steak"). Do not transliterate Georgian words — always use the correct English equivalent. '
    'Use exact culinary English terminology for ingredients. '
    'Do not add or omit any information. Preserve empty strings as empty strings. '
    'Return ONLY a valid JSON object with the exact same keys as the input. No markdown, no explanation.'
)

_SYSTEM_EN_TO_GE = (
    'You are a professional translator specializing in Georgian language and cuisine. '
    'Translate English restaurant menu content into grammatically correct, natural Georgian. '
    'Use standard literary Georgian (სალიტერატურო ქართული). '
    'Pay strict attention to verb conjugations, noun cases, and postpositions. '
    'Use natural Georgian culinary terms where they exist. '
    'Do not translate dish names already written in Georgian script — keep them as-is. '
    'Preserve empty strings as empty strings. '
    'Return ONLY a valid JSON object with the exact same keys as the input. No markdown, no explanation.'
)

_USER_PROMPT = 'Translate the following restaurant menu JSON from {source} to {target}:\n\n{content}'

_SYSTEM_GE_REVIEW = (
    'You are a Georgian language expert and editor. '
    'You will receive a JSON object whose values are Georgian text. '
    'Review each value carefully and correct any grammatical errors: '
    'noun cases (ბრუნვები), verb conjugations (ზმნის უღვლილება), postpositions (თანდებულები), '
    'and word agreement. Do not change the meaning or style — only fix grammatical mistakes. '
    'Preserve empty strings as empty strings. '
    'Return ONLY a valid JSON object with the exact same keys as the input. No markdown, no explanation.'
)


def _post_openai(payload: dict, api_key: str, verify_ssl) -> dict:
    import requests
    resp = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json=payload,
        verify=verify_ssl,
        timeout=20,
    )
    resp.raise_for_status()
    text = resp.json()['choices'][0]['message']['content'].strip()
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError('No JSON object found in OpenAI response')
    return json.loads(match.group(0))


def _call_openai(fields: dict, source_lang: str, target_lang: str, api_key: str) -> dict:
    """Translate fields. When target is Georgian, runs a second grammar-review pass."""
    try:
        import certifi
        verify = certifi.where()
    except ImportError:
        verify = True

    src = 'Georgian' if source_lang == 'ka' else 'English'
    tgt = 'Georgian' if target_lang == 'ka' else 'English'
    system = _SYSTEM_GE_TO_EN if source_lang == 'ka' else _SYSTEM_EN_TO_GE
    content = json.dumps(fields, ensure_ascii=False)

    # Step 1: translate
    translated = _post_openai({
        'model': OPENAI_MODEL,
        'messages': [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': _USER_PROMPT.format(source=src, target=tgt, content=content)},
        ],
        'temperature': 0.1,
        'max_tokens': 1024,
        'response_format': {'type': 'json_object'},
    }, api_key, verify)

    # Step 2: grammar review only when translating into Georgian
    if target_lang == 'ka':
        translated = _post_openai({
            'model': OPENAI_MODEL,
            'messages': [
                {'role': 'system', 'content': _SYSTEM_GE_REVIEW},
                {'role': 'user', 'content': json.dumps(translated, ensure_ascii=False)},
            ],
            'temperature': 0.0,
            'max_tokens': 1024,
            'response_format': {'type': 'json_object'},
        }, api_key, verify)

    return translated


def translate_item_async(item_id: int, fields: dict, source_lang: str, target_lang: str, app):
    """Translate FoodItem fields in background and update DB."""
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return

    def _run():
        try:
            result = _call_openai(fields, source_lang, target_lang, api_key)
        except Exception as exc:
            try:
                app.logger.error('[TRANSLATE] error for item %s: %s', item_id, exc)
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
    """Translate Category name/description in background and update DB."""
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return

    def _run():
        try:
            result = _call_openai(fields, source_lang, target_lang, api_key)
        except Exception as exc:
            try:
                app.logger.error('[TRANSLATE] error for category %s: %s', cat_id, exc)
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
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        return

    def _run():
        try:
            result = _call_openai(fields, source_lang, target_lang, api_key)
        except Exception as exc:
            try:
                app.logger.error('[TRANSLATE] error for GlobalItem %s: %s', item_id, exc)
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
                    item.name_ge = result.get('name') or item.name_ge
                    item.description_ge = result.get('description') or item.description_ge
                    item.ingredients_ge = result.get('ingredients') or item.ingredients_ge
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
