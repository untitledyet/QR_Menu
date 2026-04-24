"""Extract menu photo base-URLs from Google Maps Menu tab."""
import logging
import re

logger = logging.getLogger(__name__)


def _dismiss_consent(page):
    for selector in (
        'button[aria-label="Accept all"]',
        'button[aria-label="Reject all"]',
        'form[action*="consent"] button',
        'button:has-text("Accept all")',
    ):
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1500):
                btn.click()
                page.wait_for_timeout(1500)
                return
        except Exception:
            pass


def _find_menu_tab(page):
    for name in ('Menu', 'მენიუ', 'menu'):
        try:
            t = page.get_by_role('tab', name=name, exact=True)
            t.wait_for(timeout=4000)
            logger.info('[GooglePhotos] Found tab: "%s"', name)
            return t
        except Exception:
            pass
    try:
        all_tabs = page.evaluate(
            "() => Array.from(document.querySelectorAll('[role=\"tab\"]'))"
            ".map(t => t.textContent.trim())"
        )
        logger.debug('[GooglePhotos] All tabs: %s', all_tabs)
        logger.debug('[GooglePhotos] URL: %s', page.url)
    except Exception:
        pass
    return None


def extract_google_menu_photos(page, place_url, output_dir=None):
    """
    Navigate to Google Maps place, Menu tab, collect HD photo base-URLs.
    Returns list of base URL strings (without size suffix).
    """
    logger.info('[GooglePhotos] Opening place: %s', place_url)
    page.set_default_navigation_timeout(60000)
    page.goto(place_url)
    page.wait_for_timeout(4000)

    _dismiss_consent(page)

    page.reload()
    page.wait_for_timeout(5000)

    _dismiss_consent(page)

    menu_tab = _find_menu_tab(page)
    if menu_tab is None:
        page.reload()
        page.wait_for_timeout(4000)
        _dismiss_consent(page)
        menu_tab = _find_menu_tab(page)

    if menu_tab is None:
        logger.warning('[GooglePhotos] No Menu tab found')
        return []

    menu_tab.click()
    page.wait_for_timeout(4000)

    first_btn = page.locator("button[aria-label^='Photo ']").first
    try:
        first_btn.wait_for(timeout=5000)
    except Exception:
        logger.warning('[GooglePhotos] No photo buttons found')
        return []

    label = first_btn.get_attribute('aria-label')
    m = re.search(r'of (\d+)', label or '')
    if not m:
        logger.warning('[GooglePhotos] Cannot determine photo count, label=%s', label)
        return []

    total = int(m.group(1))
    logger.info('[GooglePhotos] Total photos: %d', total)

    network_urls = set()
    capturing = True

    def on_response(response):
        if not capturing:
            return
        url = response.url
        if 'lh3.googleusercontent.com' in url and '/gps-cs' in url:
            network_urls.add(url.split('=')[0])

    page.on('response', on_response)

    menu_urls = set()
    thumb_srcs = page.evaluate(
        "() => {"
        "  var btns = document.querySelectorAll(\"button[aria-label^='Photo ']\");"
        "  var urls = [];"
        "  for (var i = 0; i < btns.length; i++) {"
        "    var img = btns[i].querySelector('img[src*=\"googleusercontent\"]');"
        "    if (img && img.src) urls.push(img.src);"
        "  }"
        "  return urls;"
        "}"
    )
    for src in thumb_srcs:
        menu_urls.add(src.split('=')[0])

    photo_btns = page.locator("button[aria-label^='Photo ']")
    btn_count = photo_btns.count()
    for i in range(btn_count):
        try:
            photo_btns.nth(i).click()
            page.wait_for_timeout(2500)
            page.keyboard.press('Escape')
            page.wait_for_timeout(800)
        except Exception:
            pass

    capturing = False
    menu_urls.update(network_urls)

    gps = sorted(u for u in menu_urls if '/gps-cs' in u)
    other = sorted(u for u in menu_urls if '/gps-cs' not in u)
    final = (gps + other)[:total]

    logger.info('[GooglePhotos] Collected %d photo URLs', len(final))
    return final
