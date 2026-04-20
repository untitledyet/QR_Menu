"""Extract text menu from Google Maps Menu tab (sub-tabs)."""
import re


def extract_google_text_menu(page, place_url):
    """
    Navigate to Google Maps place, click Menu tab, extract text menu from
    all sub-tabs (e.g. ცომეული, ძირითადი კერძები, სტეიკები...).

    The Overview sub-tab usually contains photo cards — we skip it.
    We look for GEL prices inside each sub-tab individually.

    Returns dict: {category: [{name, description, price}]} or None.
    """
    print("[GoogleMenu] Opening place...")
    page.set_default_navigation_timeout(60000)
    page.goto(place_url)
    page.wait_for_timeout(4000)
    page.reload()
    page.wait_for_timeout(5000)

    # Click the top-level "Menu" tab
    menu_tab = page.get_by_role("tab", name="Menu")
    try:
        menu_tab.wait_for(timeout=8000)
    except Exception:
        print("[GoogleMenu] No Menu tab found")
        return None

    menu_tab.click()
    page.wait_for_timeout(3000)

    # Collect all sub-tab names (skip Overview / Menu / Reviews / About)
    SKIP_TABS = {"Overview", "Menu", "Reviews", "About", ""}
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

    # Filter to only non-system tabs
    content_tabs = [t for t in sub_tab_names if t not in SKIP_TABS]
    print("[GoogleMenu] Sub-tabs found: " + str(content_tabs))

    all_data = {}

    def scrape_current_tab():
        """Scroll the main panel and return its innerText."""
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
        """Parse raw innerText into list of {name, description, price}."""
        lines = [l.strip() for l in raw.split("\n") if l.strip()]

        # Find first GEL price line to anchor start
        first_gel = -1
        for i, line in enumerate(lines):
            if re.search(r"GEL\s*[\d,.]+", line):
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
            if line in skip_names or re.match(r"^GEL\s*[\d,.]+$", line):
                i += 1
                continue

            name = line
            desc_parts = []
            price = ""
            found_price_at = -1

            for j in range(i + 1, min(i + 7, len(lines))):
                gel_match = re.search(r"GEL\s*[\d,.]+", lines[j])
                if gel_match:
                    price = gel_match.group(0)
                    found_price_at = j
                    break
                if lines[j] in skip_names:
                    break
                desc_parts.append(lines[j])

            if price and name not in skip_names:
                items.append({
                    "name": name,
                    "description": ", ".join(desc_parts),
                    "price": price,
                })
                i = found_price_at + 1
            else:
                i += 1
        return items

    if content_tabs:
        # Click each sub-tab and extract
        visited = set()
        for tab_name in content_tabs:
            if tab_name in visited:
                continue
            visited.add(tab_name)

            # Skip "Overview" sub-tab — it shows photo cards, not text
            if tab_name.lower() in ("overview", "მიმოხილვა"):
                print("[GoogleMenu] Skipping Overview sub-tab (photo cards)")
                continue

            # Find and click the tab
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

            # Only parse if this tab has GEL prices (text menu)
            if "GEL" not in raw:
                print("[GoogleMenu] Sub-tab '" + tab_name + "' has no GEL prices — skipping")
                continue

            skip_set = set(SKIP_TABS) | set(content_tabs)
            items = parse_items(raw, skip_set)
            if items:
                all_data[tab_name] = items
                print("[GoogleMenu]   '" + tab_name + "': " + str(len(items)) + " items")
            else:
                print("[GoogleMenu]   '" + tab_name + "': no items parsed")
    else:
        # No sub-tabs — try the main Menu tab content directly
        raw = scrape_current_tab()
        if "GEL" in raw:
            items = parse_items(raw, SKIP_TABS)
            if items:
                all_data["Menu"] = items

    total = sum(len(v) for v in all_data.values())
    print("[GoogleMenu] Total: " + str(total) + " items in " + str(len(all_data)) + " categories")
    return all_data if total > 0 else None
