"""Extract menu from Glovo app page."""
import os
import re


def find_glovo_url(page, place_url):
    """From Google Maps place page, find the Glovo link. Returns URL or None."""
    print("[Glovo] Looking for Glovo link...")
    page.set_default_navigation_timeout(60000)
    page.goto(place_url)
    page.wait_for_timeout(4000)
    page.reload()
    page.wait_for_timeout(5000)

    url = page.evaluate(
        "() => {"
        "  var links = document.querySelectorAll('a');"
        "  for (var i = 0; i < links.length; i++) {"
        "    if ((links[i].href || '').indexOf('glovo') !== -1) return links[i].href;"
        "  }"
        "  return null;"
        "}"
    )
    if url:
        print("[Glovo] Found: " + url)
    else:
        print("[Glovo] No Glovo link found")
    return url


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
