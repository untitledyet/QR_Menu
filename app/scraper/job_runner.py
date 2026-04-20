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
            result = _run_pipeline(place_id, venue_id)
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

def _run_pipeline(place_id: str, venue_id: int) -> dict:
    from app.scraper.google_menu import extract_google_text_menu
    from app.scraper.google_photos import extract_google_menu_photos
    from app.scraper.glovo_menu import find_glovo_url, extract_glovo_menu
    from app.scraper.ai_analyzer import analyze_menu_photo, categorize_items, enrich_ingredients
    from app.scraper.merger import merge_menu
    from app.services.r2_storage import upload_from_url, upload_from_path

    maps_url = f'https://www.google.com/maps/place/?q=place_id:{place_id}&hl=en'
    tmpdir = tempfile.mkdtemp(prefix=f'scraper_{venue_id}_')

    google_text = None
    google_photo_urls = []
    google_photos_ai = None
    glovo_data = None
    glovo_photo_map = {}

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

            try:
                google_text = extract_google_text_menu(page, maps_url)
            except Exception as e:
                logger.warning(f'[ScraperJob] Google text error: {e}')

            # Screenshot for debugging
            try:
                shot_path = os.path.join(tmpdir, 'debug_after_google_text.png')
                page.screenshot(path=shot_path, full_page=False)
                shot_url = upload_from_path(shot_path, prefix=f'debug/{venue_id}')
                logger.info(f'[ScraperJob] Screenshot after google_text: {shot_url}')
            except Exception:
                pass

            try:
                google_photo_urls = extract_google_menu_photos(page, maps_url, tmpdir)
            except Exception as e:
                logger.warning(f'[ScraperJob] Google photos error: {e}')

            try:
                glovo_url = find_glovo_url(page, maps_url)
                if glovo_url:
                    gp = ctx.new_page()
                    glovo_data = extract_glovo_menu(gp, glovo_url)
                    gp.close()
            except Exception as e:
                logger.warning(f'[ScraperJob] Glovo error: {e}')

            browser.close()

        # ── Download Google photos locally for AI analysis ─────────────────
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

        # ── Glovo photos → R2 ─────────────────────────────────────────────
        if glovo_data:
            for cat, items in glovo_data.items():
                for it in items:
                    raw_url = it.get('image', '')
                    if raw_url and raw_url.startswith('http'):
                        r2_url = upload_from_url(raw_url, prefix=f'venues/{venue_id}')
                        if r2_url:
                            name_key = it.get('name', '').lower().strip()
                            glovo_photo_map[name_key] = r2_url
                            it['image'] = r2_url

        # ── AI photo analysis ──────────────────────────────────────────────
        if local_photo_paths:
            all_ai_items = []
            for path in local_photo_paths:
                try:
                    all_ai_items.extend(analyze_menu_photo(path))
                except Exception as e:
                    logger.warning(f'[ScraperJob] AI photo error {path}: {e}')

            if all_ai_items:
                has_cats = any(it.get('category') for it in all_ai_items)
                if has_cats:
                    google_photos_ai = {}
                    for it in all_ai_items:
                        cat = it.get('category') or 'მენიუ'
                        google_photos_ai.setdefault(cat, []).append(it)
                else:
                    google_photos_ai = categorize_items(all_ai_items)

            # Upload Google menu photos to R2 (for reference; analysis already done)
            for path in local_photo_paths:
                upload_from_path(path, prefix=f'venues/{venue_id}/menu_photos')

        # ── Merge ──────────────────────────────────────────────────────────
        final_menu = merge_menu(google_text, google_photos_ai, glovo_data, glovo_photo_map)

        # ── AI enrichment ──────────────────────────────────────────────────
        all_items = [it for items in final_menu.values() for it in items]

        missing_desc = sum(1 for it in all_items if not it.get('description'))
        if missing_desc:
            enrich_ingredients(all_items)

        if len(final_menu) <= 1 and len(all_items) > 5:
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
        }

        return {'_sources': sources, '_stats': stats, 'categories': final_menu}

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Library photo matching
# ---------------------------------------------------------------------------

def _match_library_photos(result: dict, GlobalItem, db):
    """Annotate each item with library_photo suggestion from GlobalItems."""
    from sqlalchemy import func
    categories = result.get('categories', {})
    for items in categories.values():
        for item in items:
            name = (item.get('name') or '').strip()
            if not name:
                continue
            match = (
                GlobalItem.query
                .filter(func.lower(GlobalItem.name) == name.lower())
                .filter(GlobalItem.image_filename.isnot(None))
                .first()
            )
            if not match:
                match = (
                    GlobalItem.query
                    .filter(GlobalItem.name.ilike(f'%{name}%'))
                    .filter(GlobalItem.image_filename.isnot(None))
                    .first()
                )
            if match:
                item['library_photo'] = match.image_filename
                item['library_photo_id'] = match.id
