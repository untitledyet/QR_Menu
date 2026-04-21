"""
Scraper job runner — triggered after venue registration.
Runs in a background thread with Flask app context.
Results are stored in ScraperJob DB table.
"""
import os
import threading
import tempfile
import shutil
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pipeline logger — accumulates steps into result_json['_log']
# ---------------------------------------------------------------------------

class PipelineLog:
    def __init__(self):
        self.entries = []

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


_pipeline_log: PipelineLog = None


def trigger_scraper_job(app, venue_id: int, place_id: str, venue_name: str):
    """Fire-and-forget: starts the scraper pipeline in a background thread."""
    if not place_id:
        return
    thread = threading.Thread(
        target=_worker,
        args=(app, venue_id, place_id, venue_name),
        daemon=True,
        name=f'scraper-{venue_id}',
    )
    thread.start()
    logger.info(f'[ScraperJob] Queued for venue_id={venue_id}')


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(place_id: str, venue_id: int, venue_name: str = '') -> dict:
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
    google_photo_urls = []
    google_photos_ai = None
    glovo_data = None
    glovo_photo_map = {}

    plog.step('პაიფლაინი დაიწყო', f'place_id={place_id}, venue_id={venue_id}')

    try:
        # ── Browser phase ──────────────────────────────────────────────────
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, slow_mo=0)
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

            # Screenshot for debugging
            try:
                shot_path = os.path.join(tmpdir, 'debug_after_google_text.png')
                page.screenshot(path=shot_path, full_page=False)
                shot_url = upload_from_path(shot_path, prefix=f'debug/{venue_id}')
                if shot_url:
                    plog.step('Debug screenshot', shot_url, 'ok', data={'url': shot_url})
                logger.info(f'[ScraperJob] Screenshot after google_text: {shot_url}')
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

            # Step 3 — Glovo (try Google Maps first, fall back to direct Glovo search)
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

        # Step 4 — Download photos
        import requests as req_lib
        local_photo_paths = []
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

        # ── Glovo photos → R2 ─────────────────────────────────────────────
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

        # Step 5 — AI photo analysis
        if local_photo_paths:
            all_ai_items = []
            for path in local_photo_paths:
                try:
                    items_from_photo = analyze_menu_photo(path)
                    all_ai_items.extend(items_from_photo)
                except Exception as e:
                    logger.warning(f'[ScraperJob] AI photo error {path}: {e}')

            plog.ai_call(
                model='gpt-4o (vision)',
                purpose=f'ფოტო ანალიზი ({len(local_photo_paths)} ფოტო)',
                prompt_preview=(
                    'Extract ALL menu items visible. Return JSON array: '
                    '[{name, description, price, category}]. '
                    'SKIP category headers, prices only, single letters.'
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
                        model='gpt-4o-mini',
                        purpose='კატეგორიზაცია',
                        prompt_preview='Categorize Georgian restaurant menu items into logical categories. Return JSON {category: [item_names]}.',
                        result_preview=f'{len(all_ai_items)} კერძი კატეგორიებში',
                    )
                    google_photos_ai = categorize_items(all_ai_items)

            # Upload Google menu photos to R2
            for path in local_photo_paths:
                upload_from_path(path, prefix=f'venues/{venue_id}/menu_photos')

        # Step 6 — Merge
        plog.step('მერჯი', 'ყველა წყაროს გაერთიანება...')
        final_menu = merge_menu(google_text, google_photos_ai, glovo_data, glovo_photo_map)
        total_after_merge = sum(len(v) for v in final_menu.values())
        plog.step(
            'მერჯი დასრულდა',
            f'{total_after_merge} კერძი — '
            + ('ტექსტი ავტორიტეტული, ფოტო AI მხოლოდ ავსებს' if google_text and sum(len(v) for v in google_text.values()) >= 15 else 'ყველა წყარო შეუწყდა'),
            'ok',
        )

        # Step 7 — AI deduplication
        all_items = [it for items in final_menu.values() for it in items]
        text_count = sum(len(v) for v in google_text.values()) if google_text else 0
        if len(all_items) > max(text_count * 1.3, 20):
            from app.scraper.ai_analyzer import ai_deduplicate
            plog.ai_call(
                model='gpt-4o-mini',
                purpose=f'დედუბლიკაცია ({len(all_items)} კერძი)',
                prompt_preview=(
                    'Identify groups of DUPLICATE items — same dish with different spellings/language. '
                    'Return array of arrays of indices. Only group when certain.'
                ),
                result_preview='...',
            )
            final_menu = ai_deduplicate(final_menu)
            all_items = [it for items in final_menu.values() for it in items]
            plog.step('დედუბლიკაცია', f'{total_after_merge} → {len(all_items)} კერძი')

        # Step 8 — Ingredient enrichment (always runs — fills 'ingredients' field)
        missing_ing = sum(1 for it in all_items if not it.get('ingredients'))
        if missing_ing:
            plog.ai_call(
                model='gpt-4o-mini',
                purpose=f'ინგრედიენტების გამდიდრება ({missing_ing} კერძი)',
                prompt_preview=(
                    'For each dish, provide typical ingredients in Georgian (3-6 words). '
                    'Return JSON {"dish_name": "ingredients"}. Drinks → empty string.'
                ),
                result_preview=f'{missing_ing} კერძს ემატება ინგრედიენტები',
            )
            enrich_ingredients(all_items)
            filled = sum(1 for it in all_items if it.get('ingredients'))
            plog.step('ინგრედიენტები', f'{filled}/{len(all_items)} კერძს აქვს ინგრედიენტები')

        if len(final_menu) <= 1 and len(all_items) > 5:
            plog.ai_call(
                model='gpt-4o-mini',
                purpose='კატეგორიზაცია (მეორე პასი)',
                prompt_preview='Categorize Georgian restaurant menu items. Return {category: [item_names]}.',
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


# ---------------------------------------------------------------------------
# Library photo matching
# ---------------------------------------------------------------------------

def _match_library_photos(result: dict, GlobalItem, db):
    """Annotate each item with library_photo suggestion using AI semantic matching."""
    from app.scraper.ai_analyzer import match_library_photos_ai
    from app.scraper import config as scraper_config

    categories = result.get('categories', {})

    # Collect all items with flat index for mapping back
    flat_items = []
    item_refs = []
    for cat_name, items in categories.items():
        for item in items:
            name = (item.get('name') or '').strip()
            if not name:
                continue
            idx = len(flat_items)
            flat_items.append({
                "i": idx,
                "name": name,
                "name_ka": item.get('name_ka', ''),
                "name_en": item.get('name_en', ''),
                "category": cat_name,
            })
            item_refs.append(item)

    if not flat_items:
        return

    # Build library from GlobalItems that have a photo
    lib_entries = GlobalItem.query.filter(GlobalItem.image_filename.isnot(None)).all()
    if not lib_entries:
        return

    r2_public = scraper_config.__dict__.get('R2_PUBLIC_URL') or ''
    try:
        import os
        r2_public = os.environ.get('R2_PUBLIC_URL', '')
    except Exception:
        pass

    library = []
    for g in lib_entries:
        image_url = f"{r2_public}/{g.image_filename}" if r2_public and g.image_filename else g.image_filename
        library.append({
            "id": g.id,
            "name": {"ka": g.name or '', "en": g.name_en or ''},
            "aliases": [],
            "image_url": image_url or '',
        })

    # AI matching in batches of 60 items
    BATCH = 60
    for i in range(0, len(flat_items), BATCH):
        batch_items = flat_items[i:i + BATCH]
        matches = match_library_photos_ai(batch_items, library)
        match_map = {m['i']: m for m in matches}
        for entry in batch_items:
            m = match_map.get(entry['i'], {})
            if m.get('match_confidence') == 'high' and m.get('matched_dish_id') is not None:
                ref = item_refs[entry['i']]
                ref['library_photo'] = m.get('matched_image_url') or ''
                ref['library_photo_id'] = m.get('matched_dish_id')
