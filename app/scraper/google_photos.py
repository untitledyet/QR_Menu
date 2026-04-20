"""Extract menu photo base-URLs from Google Maps Menu tab."""
import re


def extract_google_menu_photos(page, place_url, output_dir=None):
    """
    Navigate to Google Maps place, Menu tab, collect HD photo base-URLs.
    Returns list of base URL strings (without size suffix).
    Actual downloading is handled by saver.save_google_photos().
    """
    print("[GooglePhotos] Opening place...")
    page.set_default_navigation_timeout(60000)
    page.goto(place_url)
    page.wait_for_timeout(4000)
    page.reload()
    page.wait_for_timeout(5000)

    menu_tab = None
    for tab_name in ("Menu", "მენიუ"):
        candidate = page.get_by_role("tab", name=tab_name)
        try:
            candidate.wait_for(timeout=5000)
            menu_tab = candidate
            break
        except Exception:
            pass
    if menu_tab is None:
        print("[GooglePhotos] No Menu tab")
        return []

    menu_tab.click()
    page.wait_for_timeout(4000)

    first_btn = page.locator("button[aria-label^='Photo ']").first
    try:
        first_btn.wait_for(timeout=5000)
    except Exception:
        print("[GooglePhotos] No photo buttons found")
        return []

    label = first_btn.get_attribute("aria-label")
    m = re.search(r"of (\d+)", label or "")
    if not m:
        print("[GooglePhotos] Cannot determine photo count")
        return []

    total = int(m.group(1))
    print("[GooglePhotos] Total photos: " + str(total))

    # Capture network responses for HD URLs
    network_urls = set()
    capturing = True

    def on_response(response):
        if not capturing:
            return
        url = response.url
        if "lh3.googleusercontent.com" in url and "/gps-cs" in url:
            network_urls.add(url.split("=")[0])

    page.on("response", on_response)

    # Collect thumbnail base URLs
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
        menu_urls.add(src.split("=")[0])

    # Click each photo to trigger HD network loads
    photo_btns = page.locator("button[aria-label^='Photo ']")
    btn_count = photo_btns.count()
    for i in range(btn_count):
        try:
            photo_btns.nth(i).click()
            page.wait_for_timeout(2500)
            page.keyboard.press("Escape")
            page.wait_for_timeout(800)
        except Exception:
            pass

    capturing = False
    menu_urls.update(network_urls)

    # Prioritize /gps-cs URLs, cap at `total`
    gps = sorted(u for u in menu_urls if "/gps-cs" in u)
    other = sorted(u for u in menu_urls if "/gps-cs" not in u)
    final = (gps + other)[:total]

    print("[GooglePhotos] Collected " + str(len(final)) + " photo URLs")
    return final
