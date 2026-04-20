"""Extract menu from Glovo app page."""
import os
import re


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
    """Search all links + text nodes for a glovo URL. Returns URL or None."""
    return page.evaluate(
        "() => {"
        "  var found = null;"
        "  var links = document.querySelectorAll('a');"
        "  for (var i = 0; i < links.length; i++) {"
        "    var href = links[i].href || '';"
        "    if (href.indexOf('glovo') !== -1 || href.indexOf('glovoapp') !== -1) {"
        "      found = href; break;"
        "    }"
        "    var txt = links[i].textContent || '';"
        "    if (txt.toLowerCase().indexOf('glovo') !== -1) {"
        "      found = href || links[i].textContent.trim(); break;"
        "    }"
        "  }"
        "  if (!found) {"
        "    var all = document.querySelectorAll('[data-value], [href], button, span, div');"
        "    for (var j = 0; j < all.length; j++) {"
        "      var dv = all[j].getAttribute('data-value') || '';"
        "      if (dv.indexOf('glovo') !== -1) { found = dv; break; }"
        "    }"
        "  }"
        "  return found;"
        "}"
    )


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

    # Log all <a> hrefs for debugging
    try:
        all_hrefs = page.evaluate(
            "() => Array.from(document.querySelectorAll('a[href]'))"
            ".map(a => a.href).filter(h => h.startsWith('http')).slice(0, 30)"
        )
        print("[Glovo] All external links found: " + str(all_hrefs))
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
