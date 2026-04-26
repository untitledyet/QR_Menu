"""Scraper pipeline runner.

Entry points:
  * `trigger_scraper_job(app, venue_id, place_id, venue_name)` — fire-and-forget
    from a web request. Dispatches to RQ when REDIS_URL is present, falls back
    to a background thread otherwise.
  * `_worker(app, venue_id, place_id, venue_name)` — the actual unit of work.
    Invoked by both the thread path and the RQ worker (see queue.py).

The pipeline itself is unchanged in shape (Google text → Google photos → Glovo
→ AI merge → dedup → enrich), but each stage now uses:
  * ai_analyzer.py with Responses API + structured outputs
  * image_preprocessor.py before any vision call
  * embeddings for dedup and library matching
  * r2_storage with content-addressable compression
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════════════
# Pipeline log — accumulated into ScraperJob.result_json['_log']
# ═════════════════════════════════════════════════════════════════════════════

class PipelineLog:
    def __init__(self):
        self.entries: list = []

    def step(self, title: str, detail: str = '', status: str = 'ok', data=None):
        entry = {
            'ts': datetime.utcnow().strftime('%H:%M:%S'),
            'title': title,
            'detail': detail,
            'status': status,  # ok | warn | error | ai
        }
        if data:
            entry['data'] = data
        self.entries.append(entry)
        icon = {'ok': '✓', 'warn': '⚠', 'error': '✗', 'ai': '🤖'}.get(status, '·')
        print(f"[Pipeline] {icon} {title}" + (f" — {detail}" if detail else ""))

    def ai_call(self, model: str, purpose: str, prompt_preview: str, result_preview: str):
        self.step(
            title=f'AI: {purpose}',
            detail=f'model={model}',
            status='ai',
            data={'prompt': prompt_preview[:300], 'result': result_preview[:300]},
        )


# ═════════════════════════════════════════════════════════════════════════════
# Dispatch
# ═════════════════════════════════════════════════════════════════════════════

def trigger_scraper_job(app, venue_id: int, place_id: str, venue_name: str) -> str:
    """Fire-and-forget: dispatch the pipeline via RQ (if available) or thread."""
    if not place_id:
        return ''
    from app.scraper.queue import enqueue_scraper_job
    return enqueue_scraper_job(app, venue_id, place_id, venue_name)


# ═════════════════════════════════════════════════════════════════════════════
# Worker — called by both thread and RQ paths
# ═════════════════════════════════════════════════════════════════════════════

def _worker(app, venue_id: int, place_id: str, venue_name: str):
    with app.app_context():
        from app import db
        from app.models import ScraperJob, GlobalItem

        job = ScraperJob.query.filter_by(venue_id=venue_id).first()
        if not job:
            job = ScraperJob(venue_id=venue_id)
            db.session.add(job)
        job.status = 'running'
        job.error_message = None
        db.session.commit()

        try:
            result = _run_pipeline(place_id, venue_id, venue_name)
            _match_library_photos(result, GlobalItem, db)
            job.status = 'done'
            job.result_json = result
            job.sources_found = result.get('_sources', {})
            total = result.get('_stats', {}).get('total_items', 0)
            logger.info(f'[ScraperJob] Done venue_id={venue_id} — {total} items')
        except Exception:
            logger.exception(f'[ScraperJob] Failed for venue_id={venue_id}')
            job.status = 'failed'
            import traceback
            job.error_message = traceback.format_exc()[-2000:]
        finally:
            job.finished_at = datetime.utcnow()
            db.session.commit()


# ═════════════════════════════════════════════════════════════════════════════
# Pipeline
# ═════════════════════════════════════════════════════════════════════════════

def _run_pipeline(place_id: str, venue_id: int, venue_name: str = '') -> dict:
    from app.scraper import config as scraper_config
    from app.scraper.google_menu import extract_google_text_menu
    from app.scraper.google_photos import extract_google_menu_photos
    from app.scraper.glovo_menu import find_glovo_url, find_glovo_url_direct, extract_glovo_menu
    from app.scraper.ai_analyzer import analyze_menu_photo, categorize_items, enrich_ingredients
    from app.scraper.merger import merge_menu
    from app.services.r2_storage import upload_from_url, upload_from_path

    plog = PipelineLog()
    maps_url = f'https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en'
    tmpdir = tempfile.mkdtemp(prefix=f'scraper_{venue_id}_')

    google_text = None
    google_photo_urls: list = []
    google_photos_ai = None
    glovo_data = None
    glovo_photo_map: dict = {}

    plog.step('პაიფლაინი დაიწყო', f'place_id={place_id}, venue_id={venue_id}')

    try:
        # ── Browser phase ──────────────────────────────────────────────────
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=scraper_config.HEADLESS,
                slow_mo=scraper_config.SLOW_MO,
            )
            ctx = browser.new_context(
                viewport={'width': 1280, 'height': 900},
                locale='en-US',
                timezone_id='America/New_York',
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/124.0.0.0 Safari/537.36'
                ),
            )
            page = ctx.new_page()

            # Step 1 — Google Maps text menu
            plog.step('Google Maps გახსნა', maps_url)
            try:
                google_text = extract_google_text_menu(page, maps_url)
                if google_text:
                    total_t = sum(len(v) for v in google_text.values())
                    cats = list(google_text.keys())
                    plog.step(
                        'Google Maps ტექსტური მენიუ',
                        f'{total_t} კერძი, {len(cats)} კატეგორია',
                        'ok',
                        data={'categories': {k: len(v) for k, v in google_text.items()}},
                    )
                else:
                    plog.step('Google Maps ტექსტური მენიუ', 'Menu tab ვერ მოიძებნა', 'warn')
            except Exception as e:
                plog.step('Google Maps ტექსტური მენიუ', str(e), 'error')
                logger.warning(f'[ScraperJob] Google text error: {e}')

            # Debug screenshot — full PNG, no compression
            try:
                shot_path = os.path.join(tmpdir, 'debug_after_google_text.png')
                page.screenshot(path=shot_path, full_page=False)
                shot_url = upload_from_path(
                    shot_path, prefix=f'debug/{venue_id}', no_compress=True,
                )
                if shot_url:
                    plog.step('Debug screenshot', shot_url, 'ok', data={'url': shot_url})
            except Exception:
                pass

            # Step 2 — Google menu photos
            try:
                google_photo_urls = extract_google_menu_photos(page, maps_url, tmpdir)
                plog.step(
                    'Google Maps ფოტოები',
                    f'{len(google_photo_urls)} ფოტო მოძიებულია' if google_photo_urls else 'ფოტოები ვერ მოიძებნა',
                    'ok' if google_photo_urls else 'warn',
                )
            except Exception as e:
                plog.step('Google Maps ფოტოები', str(e), 'error')
                logger.warning(f'[ScraperJob] Google photos error: {e}')

            # Step 3 — Glovo
            try:
                glovo_url = find_glovo_url(page, maps_url)
                if not glovo_url and venue_name:
                    plog.step('Glovo (Google Maps)', 'ვერ მოიძებნა — პირდაპირ ვეძებ Glovo.com-ზე', 'warn')
                    gp_search = ctx.new_page()
                    glovo_url = find_glovo_url_direct(gp_search, venue_name)
                    gp_search.close()

                if glovo_url:
                    plog.step('Glovo ბმული', glovo_url, 'ok')
                    gp = ctx.new_page()
                    glovo_data = extract_glovo_menu(gp, glovo_url)
                    gp.close()
                    if glovo_data:
                        total_g = sum(len(v) for v in glovo_data.values())
                        plog.step('Glovo მენიუ', f'{total_g} კერძი {len(glovo_data)} კატეგორიაში', 'ok')
                    else:
                        plog.step('Glovo მენიუ', 'კერძები ვერ ამოიღო', 'warn')
                else:
                    plog.step('Glovo', 'ბმული ვერ მოიძებნა (Google Maps + Glovo.com ძიება)', 'warn')
            except Exception as e:
                plog.step('Glovo', str(e), 'error')
                logger.warning(f'[ScraperJob] Glovo error: {e}')

            browser.close()

        # ── Download Google photos ────────────────────────────────────────
        import requests as req_lib
        local_photo_paths: list = []
        for i, base_url in enumerate(google_photo_urls):
            dest = os.path.join(tmpdir, f'gphoto_{i+1:03d}.jpg')
            try:
                r = req_lib.get(base_url + '=w2000', timeout=15)
                if r.status_code == 200 and len(r.content) >= 5000:
                    with open(dest, 'wb') as fh:
                        fh.write(r.content)
                    local_photo_paths.append(dest)
            except Exception:
                pass
        plog.step('ფოტოები ჩამოიტვირთა', f'{len(local_photo_paths)}/{len(google_photo_urls)} წარმატებით')

        # ── Glovo photos → R2 (content-addressable dedup handled inside) ──
        if glovo_data:
            uploaded = 0
            for cat, items in glovo_data.items():
                for it in items:
                    raw_url = it.get('image', '')
                    if raw_url and raw_url.startswith('http'):
                        r2_url = upload_from_url(raw_url, prefix=f'venues/{venue_id}')
                        if r2_url:
                            name_key = it.get('name', '').lower().strip()
                            glovo_photo_map[name_key] = r2_url
                            it['image'] = r2_url
                            uploaded += 1
            plog.step('Glovo ფოტოები R2-ზე', f'{uploaded} ფოტო ატვირთული')

        # ── AI photo analysis ─────────────────────────────────────────────
        if local_photo_paths:
            all_ai_items: list = []
            for path in local_photo_paths:
                try:
                    items_from_photo = analyze_menu_photo(path)
                    all_ai_items.extend(items_from_photo)
                except Exception as e:
                    logger.warning(f'[ScraperJob] AI photo error {path}: {e}')

            plog.ai_call(
                model=scraper_config.OPENAI_MODEL_VISION,
                purpose=f'ფოტო ანალიზი ({len(local_photo_paths)} ფოტო)',
                prompt_preview=(
                    'Vision extraction via Responses API (json_schema). '
                    'Returns flat array of {name, price, description, category}.'
                ),
                result_preview=f'{len(all_ai_items)} კერძი ამოღებული {len(local_photo_paths)} ფოტოდან',
            )

            if all_ai_items:
                has_cats = any(it.get('category') for it in all_ai_items)
                if has_cats:
                    google_photos_ai = {}
                    for it in all_ai_items:
                        cat = it.get('category') or 'მენიუ'
                        google_photos_ai.setdefault(cat, []).append(it)
                    plog.step('ფოტო AI კატეგორიები', f'{len(google_photos_ai)} კატეგორია (GPT-დან)')
                else:
                    plog.ai_call(
                        model=scraper_config.OPENAI_MODEL_FAST,
                        purpose='კატეგორიზაცია',
                        prompt_preview='Grouping un-categorised items into logical buckets (structured).',
                        result_preview=f'{len(all_ai_items)} კერძი კატეგორიებში',
                    )
                    google_photos_ai = categorize_items(all_ai_items)

            # Upload the downloaded menu photos (compressed) to R2
            for path in local_photo_paths:
                upload_from_path(path, prefix=f'venues/{venue_id}/menu_photos')

        # ── Merge all sources ─────────────────────────────────────────────
        plog.step('მერჯი', 'ყველა წყაროს გაერთიანება...')
        final_menu = merge_menu(google_text, google_photos_ai, glovo_data, glovo_photo_map)
        total_after_merge = sum(len(v) for v in final_menu.values())
        plog.step(
            'მერჯი დასრულდა',
            f'{total_after_merge} კერძი — '
            + ('ტექსტი ავტორიტეტული, ფოტო AI მხოლოდ ავსებს'
               if google_text and sum(len(v) for v in google_text.values()) >= 15
               else 'ყველა წყარო შეუწყდა'),
            'ok',
        )

        # ── Embedding-based deduplication ─────────────────────────────────
        all_items = [it for items in final_menu.values() for it in items]
        text_count = sum(len(v) for v in google_text.values()) if google_text else 0
        if len(all_items) > max(text_count * 1.3, 20):
            from app.scraper.ai_analyzer import ai_deduplicate
            plog.ai_call(
                model=scraper_config.OPENAI_MODEL_EMBED,
                purpose=f'დედუბლიკაცია ({len(all_items)} კერძი)',
                prompt_preview='Embedding-based cosine similarity (threshold 0.88).',
                result_preview='...',
            )
            final_menu = ai_deduplicate(final_menu)
            all_items = [it for items in final_menu.values() for it in items]
            plog.step('დედუბლიკაცია', f'{total_after_merge} → {len(all_items)} კერძი')

        # ── Ingredient enrichment ─────────────────────────────────────────
        missing_ing = sum(1 for it in all_items if not it.get('ingredients'))
        if missing_ing:
            plog.ai_call(
                model=scraper_config.OPENAI_MODEL_FAST,
                purpose=f'ინგრედიენტების გამდიდრება ({missing_ing} კერძი)',
                prompt_preview='Ingredient enrichment via structured JSON schema.',
                result_preview=f'{missing_ing} კერძს ემატება ინგრედიენტები',
            )
            enrich_ingredients(all_items)
            filled = sum(1 for it in all_items if it.get('ingredients'))
            plog.step('ინგრედიენტები', f'{filled}/{len(all_items)} კერძს აქვს ინგრედიენტები')

        # Second-pass categorization if needed
        if len(final_menu) <= 1 and len(all_items) > 5:
            plog.ai_call(
                model=scraper_config.OPENAI_MODEL_FAST,
                purpose='კატეგორიზაცია (მეორე პასი)',
                prompt_preview='Fallback grouping of flat item list.',
                result_preview='...',
            )
            final_menu = categorize_items(all_items)
            all_items = [it for items in final_menu.values() for it in items]

        sources = {
            'google_text': bool(google_text),
            'google_photos': bool(google_photo_urls),
            'glovo': bool(glovo_data),
        }
        stats = {
            'total_items': len(all_items),
            'items_with_price': sum(1 for it in all_items if it.get('price')),
            'items_with_photo': sum(1 for it in all_items if it.get('image')),
            'items_with_desc': sum(1 for it in all_items if it.get('description')),
            'items_with_ingredients': sum(1 for it in all_items if it.get('ingredients')),
        }

        plog.step(
            'პაიფლაინი დასრულდა ✓',
            f"{stats['total_items']} კერძი | {stats['items_with_price']} ფასით | "
            f"{stats['items_with_desc']} აღწერით | {stats['items_with_photo']} ფოტოთი",
            'ok',
        )

        return {'_sources': sources, '_stats': stats, 'categories': final_menu, '_log': plog.entries}

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ═════════════════════════════════════════════════════════════════════════════
# Library photo matching — embedding-backed
# ═════════════════════════════════════════════════════════════════════════════

def _match_library_photos(result: dict, GlobalItem, db):
    """Annotate each result item with library_photo suggestion."""
    from app.scraper.ai_analyzer import match_library_photos_ai

    categories = result.get('categories', {})

    flat_items: list = []
    item_refs: list = []
    for cat_name, items in categories.items():
        for item in items:
            name = (item.get('name') or '').strip()
            if not name:
                continue
            idx = len(flat_items)
            flat_items.append({
                'i': idx,
                'name': name,
                'name_ka': item.get('name_ka', ''),
                'name_en': item.get('name_en', ''),
                'category': cat_name,
            })
            item_refs.append(item)

    if not flat_items:
        return

    lib_entries = GlobalItem.query.filter(GlobalItem.image_filename.isnot(None)).all()
    if not lib_entries:
        return

    r2_public = os.environ.get('R2_PUBLIC_URL', '').rstrip('/')
    library = []
    for g in lib_entries:
        if r2_public and g.image_filename and not g.image_filename.startswith('http'):
            image_url = f'{r2_public}/{g.image_filename}'
        else:
            image_url = g.image_filename or ''
        library.append({
            'id': g.id,
            'name': {'ka': g.name_ge or '', 'en': g.name_en or ''},
            'aliases': g.tags_list,
            'image_url': image_url,
        })

    # Embedding-based matching — one call for everything, no batching needed
    try:
        matches = match_library_photos_ai(flat_items, library)
    except Exception as e:
        logger.warning(f'[ScraperJob] library match failed: {e}')
        return

    for m in matches:
        i = m.get('i')
        if i is None or i >= len(item_refs):
            continue
        ref = item_refs[i]
        ref['library_photo'] = m.get('matched_image_url') or ''
        ref['library_photo_id'] = m.get('matched_dish_id')
