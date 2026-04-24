"""Extract menu from Glovo app page."""
import os
import re


# Georgian city slugs to try on Glovo
_GE_CITIES = ['tbilisi', 'batumi', 'rustavi', 'kutaisi', 'gori', 'zugdidi', 'telavi']


def find_glovo_url_direct(page, venue_name: str) -> str | None:
    """
    Search Glovo website directly by venue name — bypasses Google Maps geo-restriction.
    Tries Georgian Glovo search for each city until a match is found.
    Returns the restaurant page URL or None.
    """
    print(f"[Glovo] Direct search for: '{venue_name}'")
    page.set_default_navigation_timeout(60000)

    # Glovo search URL — Georgian locale
    search_query = venue_name.strip().split()[0]  # use first word for better match
    search_url = f'https://glovoapp.com/ge/ka/search/?q={search_query}'
    print(f"[Glovo] Search URL: {search_url}")

    try:
        page.goto(search_url)
        page.wait_for_timeout(5000)

        # Dismiss cookie/address popups
        for sel in (
            'button[data-testid="address-modal-close"]',
            'button[aria-label="Close"]',
            'button:has-text("Accept")',
            'button:has-text("Accept all")',
            '[data-testid="modal-close"]',
        ):
            try:
                b = page.locator(sel).first
                if b.is_visible(timeout=1000):
                    b.click()
                    page.wait_for_timeout(800)
            except Exception:
                pass

        # Look for restaurant links in search results
        url = page.evaluate(
            "() => {"
            "  var links = document.querySelectorAll('a[href*=\"/ge/ka/\"]');"
            "  for (var i = 0; i < links.length; i++) {"
            "    var href = links[i].href || '';"
            "    var txt = (links[i].textContent || '').trim().toLowerCase();"
            "    if (href && txt && txt.length > 2) return href;"
            "  }"
            "  return null;"
            "}"
        )

        if url:
            print(f"[Glovo] Direct search found: {url}")
            return url

        # Also try raw HTML regex
        html = page.content()
        m = re.search(r'https?://glovoapp\.com/ge/ka/[^"\'<>\s]+', html)
        if m:
            result = m.group(0)
            print(f"[Glovo] Direct search (regex) found: {result}")
            return result

        print(f"[Glovo] Direct search — no results for '{search_query}'")

    except Exception as e:
        print(f"[Glovo] Direct search error: {e}")

    return None


def _dismiss_consent(page):
    for selector in (
        'button[aria-label="Accept all"]',
        'button[aria-label="Reject all"]',
        'form[action*="consent"] button',
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
    ):
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1500):
                btn.click()
                page.wait_for_timeout(1500)
                return
        except Exception:
            pass


def _search_glovo_in_page(page):
    """Search all links, attributes, and raw HTML for a glovo URL. Returns URL or None."""
    # 1. Standard <a> href search
    url = page.evaluate(
        "() => {"
        "  var links = document.querySelectorAll('a');"
        "  for (var i = 0; i < links.length; i++) {"
        "    var href = links[i].href || '';"
        "    if (href.indexOf('glovo') !== -1) return href;"
        "    if ((links[i].textContent||'').toLowerCase().indexOf('glovo') !== -1 && href) return href;"
        "  }"
        "  return null;"
        "}"
    )
    if url:
        return url

    # 2. Search ALL element attributes for glovo
    url = page.evaluate(
        "() => {"
        "  var all = document.querySelectorAll('*');"
        "  for (var i = 0; i < all.length; i++) {"
        "    var attrs = all[i].attributes;"
        "    for (var j = 0; j < attrs.length; j++) {"
        "      var v = attrs[j].value || '';"
        "      if (v.indexOf('glovo') !== -1) return v;"
        "    }"
        "  }"
        "  return null;"
        "}"
    )
    if url:
        return url

    # 3. Extract glovo URL from raw page HTML using regex
    import re
    try:
        html = page.content()
        m = re.search(r'https?://[^"\'<>\s]*glovoapp[^"\'<>\s]*', html)
        if m:
            return m.group(0)
        # Also match generic glovo.com
        m2 = re.search(r'https?://[^"\'<>\s]*glovo[^"\'<>\s]*', html)
        if m2:
            return m2.group(0)
    except Exception:
        pass

    return None


def find_glovo_url(page, place_url):
    """From Google Maps place page, find the Glovo link. Returns URL or None."""
    print("[Glovo] Looking for Glovo link on: " + place_url)
    page.set_default_navigation_timeout(60000)
    page.goto(place_url)
    page.wait_for_timeout(4000)
    _dismiss_consent(page)
    page.reload()
    page.wait_for_timeout(5000)
    _dismiss_consent(page)

    # Try scrolling to lazy-load content (About section is below the fold)
    for _ in range(10):
        page.evaluate("() => { var m = document.querySelector('[role=\"main\"]'); if(m) m.scrollTop += 300; else window.scrollBy(0,300); }")
        page.wait_for_timeout(300)

    url = _search_glovo_in_page(page)
    if url:
        print("[Glovo] Found after scroll: " + url)
        return url

    # Try clicking About tab to reveal ordering links
    for tab_name in ('About', 'მიმოხილვა', 'Overview'):
        try:
            tab = page.get_by_role('tab', name=tab_name, exact=True)
            if tab.count() > 0 and tab.first.is_visible(timeout=2000):
                tab.first.click()
                page.wait_for_timeout(3000)
                print(f"[Glovo] Clicked '{tab_name}' tab, searching again...")
                url = _search_glovo_in_page(page)
                if url:
                    print("[Glovo] Found after tab click: " + url)
                    return url
        except Exception:
            pass

    # Debug: log all external links and search raw HTML for "order"/"delivery" keywords
    try:
        all_hrefs = page.evaluate(
            "() => Array.from(document.querySelectorAll('a[href]'))"
            ".map(a => a.href).filter(h => h.startsWith('http')).slice(0, 30)"
        )
        print("[Glovo] All external links: " + str(all_hrefs))
    except Exception:
        pass

    try:
        html = page.content()
        order_keywords = ['glovo', 'wolt', 'bolt food', 'delivery', 'order']
        for kw in order_keywords:
            idx = html.lower().find(kw)
            if idx >= 0:
                snippet = html[max(0, idx-80):idx+120].replace('\n', ' ')
                print(f"[Glovo] HTML snippet around '{kw}': ...{snippet}...")
    except Exception:
        pass

    print("[Glovo] No Glovo link found")
    return None


def extract_glovo_menu(page, glovo_url):
    """Open Glovo page and extract menu. Returns dict or None."""
    js_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glovo_extract.js")
    with open(js_path, "r", encoding="utf-8") as f:
        js_code = f.read()

    print("[Glovo] Opening " + glovo_url)
    page.set_default_navigation_timeout(60000)
    page.goto(glovo_url)
    page.wait_for_timeout(5000)

    # Close popups
    for btn_name in ["დახურვა", "უარყოფა", "address-close", "Accept", "Got it", "Close"]:
        try:
            btn = page.get_by_role("button", name=btn_name)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(800)
        except:
            pass

    # Scroll to load all
    prev_h = 0
    for _ in range(60):
        page.evaluate("() => window.scrollBy(0, 500)")
        page.wait_for_timeout(400)
        new_h = page.evaluate("() => document.body.scrollHeight")
        if new_h == prev_h:
            break
        prev_h = new_h

    page.evaluate("() => window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

    print("[Glovo] Extracting menu...")
    data = page.evaluate(js_code)

    # Clean: remove empty categories and "ხშირად დასმული კითხვები"
    cleaned = {}
    for cat, items in data.items():
        if not items:
            continue
        if "კითხვ" in cat.lower() or "faq" in cat.lower():
            continue
        cleaned[cat] = items

    total = sum(len(v) for v in cleaned.values())
    print("[Glovo] Total: " + str(total) + " items in " + str(len(cleaned)) + " categories")
    return cleaned if total > 0 else None
