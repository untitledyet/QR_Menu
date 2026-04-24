"""Extract text menu from Google Maps Menu tab (sub-tabs)."""
import re


def _dismiss_consent(page):
    """Click Google's cookie/consent accept button if present."""
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
                print(f'[GoogleMenu] Dismissed consent via: {selector}')
                return
        except Exception:
            pass


def _find_menu_tab(page):
    """Find the Menu tab by ARIA role or text content. Returns locator or None."""
    # 1. Try standard ARIA tab with various names
    for name in ('Menu', 'მენიუ', 'menu', 'MENU'):
        try:
            t = page.get_by_role('tab', name=name, exact=True)
            t.wait_for(timeout=4000)
            print(f'[GoogleMenu] Found tab by role name="{name}"')
            return t
        except Exception:
            pass

    # 2. Log all tab names for debugging
    try:
        all_tabs = page.evaluate(
            "() => Array.from(document.querySelectorAll('[role=\"tab\"]'))"
            ".map(t => t.textContent.trim())"
        )
        print(f'[GoogleMenu] All tabs on page: {all_tabs}')
    except Exception:
        pass

    # 3. Fallback — find any element containing "menu" text (case-insensitive)
    for selector in (
        'button[jsaction*="menu"]',
        '[data-tab-index] button',
        'div[role="tablist"] button',
    ):
        try:
            els = page.locator(selector).all()
            for el in els:
                txt = el.text_content() or ''
                if 'menu' in txt.lower() or 'მენიუ' in txt:
                    print(f'[GoogleMenu] Found menu element via fallback selector: "{txt.strip()}"')
                    return el
        except Exception:
            pass

    # 4. Log page URL and title for debugging
    try:
        print(f'[GoogleMenu] Page URL: {page.url}')
        print(f'[GoogleMenu] Page title: {page.title()}')
    except Exception:
        pass

    return None


def extract_google_text_menu(page, place_url):
    """
    Navigate to Google Maps place, click Menu tab, extract text menu from
    all sub-tabs (e.g. ცომეული, ძირითადი კერძები, სტეიკები...).

    Returns dict: {category: [{name, description, price}]} or None.
    """
    print('[GoogleMenu] Opening place: ' + place_url)
    page.set_default_navigation_timeout(60000)
    page.goto(place_url)
    page.wait_for_timeout(4000)

    _dismiss_consent(page)

    page.reload()
    page.wait_for_timeout(5000)

    _dismiss_consent(page)

    print(f'[GoogleMenu] After load — URL: {page.url}')
    print(f'[GoogleMenu] After load — Title: {page.title()}')

    menu_tab = _find_menu_tab(page)
    if menu_tab is None:
        # Try one more reload
        page.reload()
        page.wait_for_timeout(4000)
        _dismiss_consent(page)
        print(f'[GoogleMenu] After 2nd reload — URL: {page.url}')
        menu_tab = _find_menu_tab(page)

    if menu_tab is None:
        print('[GoogleMenu] No Menu tab found after all attempts')
        return None

    menu_tab.click()
    page.wait_for_timeout(3000)

    # Collect all sub-tab names
    SKIP_TABS = {'Overview', 'Menu', 'Reviews', 'About', 'მიმოხილვა', 'მენიუ', 'შეფასებები', ''}
    sub_tab_names = page.evaluate(
        "() => {"
        "  var tabs = document.querySelectorAll('[role=\"tablist\"] [role=\"tab\"]');"
        "  var result = [];"
        "  for (var i = 0; i < tabs.length; i++) {"
        "    var txt = tabs[i].textContent.trim();"
        "    result.push(txt);"
        "  }"
        "  return result;"
        "}"
    )
    content_tabs = [t for t in sub_tab_names if t not in SKIP_TABS]
    print('[GoogleMenu] Sub-tabs found: ' + str(content_tabs))

    all_data = {}

    def scrape_current_tab():
        page.evaluate(
            "() => { var m = document.querySelector('[role=\"main\"]'); if(m) m.scrollTop = 0; }"
        )
        page.wait_for_timeout(400)
        for _ in range(20):
            page.evaluate(
                "() => { var m = document.querySelector('[role=\"main\"]'); if(m) m.scrollTop += 400; }"
            )
            page.wait_for_timeout(300)
        return page.evaluate(
            "() => { var m = document.querySelector('[role=\"main\"]'); return m ? m.innerText : ''; }"
        )

    def parse_items(raw, skip_names):
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        first_gel = -1
        for i, line in enumerate(lines):
            if re.search(r'GEL\s*[\d,.]+', line):
                first_gel = i
                break
        if first_gel < 0:
            return []
        start = max(0, first_gel - 2)
        lines = lines[start:]
        items = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line in skip_names or re.match(r'^GEL\s*[\d,.]+$', line):
                i += 1
                continue
            name = line
            desc_parts = []
            price = ''
            found_price_at = -1
            for j in range(i + 1, min(i + 7, len(lines))):
                gel_match = re.search(r'GEL\s*[\d,.]+', lines[j])
                if gel_match:
                    price = gel_match.group(0)
                    found_price_at = j
                    break
                if lines[j] in skip_names:
                    break
                desc_parts.append(lines[j])
            if price and name not in skip_names:
                items.append({
                    'name': name,
                    'description': ', '.join(desc_parts),
                    'price': price,
                })
                i = found_price_at + 1
            else:
                i += 1
        return items

    if content_tabs:
        visited = set()
        for tab_name in content_tabs:
            if tab_name in visited:
                continue
            visited.add(tab_name)
            if tab_name.lower() in ('overview', 'მიმოხილვა'):
                print('[GoogleMenu] Skipping Overview sub-tab')
                continue
            sub_tabs = page.locator('[role="tablist"] [role="tab"]')
            count = sub_tabs.count()
            clicked = False
            for idx in range(count):
                t = sub_tabs.nth(idx)
                if t.text_content().strip() == tab_name:
                    t.click()
                    page.wait_for_timeout(2000)
                    clicked = True
                    break
            if not clicked:
                continue
            raw = scrape_current_tab()
            if 'GEL' not in raw:
                print("[GoogleMenu] Sub-tab '" + tab_name + "' has no GEL prices — skipping")
                continue
            skip_set = set(SKIP_TABS) | set(content_tabs)
            items = parse_items(raw, skip_set)
            if items:
                all_data[tab_name] = items
                print('[GoogleMenu]   \'' + tab_name + '\': ' + str(len(items)) + ' items')
            else:
                print('[GoogleMenu]   \'' + tab_name + '\': no items parsed')
    else:
        raw = scrape_current_tab()
        print(f'[GoogleMenu] Main tab raw length: {len(raw)} chars, GEL present: {"GEL" in raw}')
        if 'GEL' in raw:
            items = parse_items(raw, SKIP_TABS)
            if items:
                all_data['Menu'] = items

    total = sum(len(v) for v in all_data.values())
    print('[GoogleMenu] Total: ' + str(total) + ' items in ' + str(len(all_data)) + ' categories')
    return all_data if total > 0 else None
