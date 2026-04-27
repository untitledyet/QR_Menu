"""Debug a single menu photo through the full import pipeline.

Shows: OCR text → extracted items → library photo matches

Usage:
    python scripts/debug_import.py path/to/menu.jpg
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(image_path: str):
    from dotenv import load_dotenv
    load_dotenv()

    from app import create_app
    from app.models import GlobalItem

    app = create_app()

    with app.app_context():
        from app.scraper.ai_analyzer import analyze_menu_photo_structured
        from app.scraper.embeddings import match_library_photos

        print(f'\n{"═"*60}')
        print(f'  IMAGE: {os.path.basename(image_path)}')
        print(f'{"═"*60}\n')

        # ── Step 1: OCR + parse ───────────────────────────────────
        print('STEP 1: OCR + PARSE')
        print('─' * 40)

        ocr_text_holder = []

        def event_cb(kind, **kw):
            if kind == 'ocr_done':
                ocr_text_holder.append(kw.get('text', ''))
            elif kind == 'parse_done':
                pass

        items = analyze_menu_photo_structured(image_path, event_cb=event_cb)

        if ocr_text_holder:
            print('OCR TEXT:')
            print(ocr_text_holder[0])
            print()

        print(f'EXTRACTED ITEMS ({len(items)}):')
        for i, it in enumerate(items, 1):
            print(f'  {i:2}. [{it.get("category","?"):20}] {it.get("name",""):40}  ₾{it.get("price","?"):>6}')
        print()

        if not items:
            print('No items extracted.')
            return

        # ── Step 2: Library matching ──────────────────────────────
        print('STEP 2: LIBRARY PHOTO MATCHING')
        print('─' * 40)

        lib_entries = GlobalItem.query.filter(GlobalItem.image_filename.isnot(None)).all()
        print(f'Library size: {len(lib_entries)} items with photos\n')

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

        menu_for_match = [
            {'i': i, 'name': it['name'],
             'name_ka': it.get('name_ka', ''), 'name_en': it.get('name_en', ''),
             'category': it.get('category', '')}
            for i, it in enumerate(items)
        ]

        matches = match_library_photos(menu_for_match, library)
        match_map = {m['i']: m for m in matches}

        print(f'{"#":>3}  {"ITEM NAME":40}  {"MATCH":6}  {"CONFIDENCE":10}  LIBRARY ENTRY')
        print('─' * 100)
        matched = 0
        for i, it in enumerate(items):
            m = match_map.get(i)
            if m:
                lib_entry = next((g for g in lib_entries if g.id == m.get('matched_dish_id')), None)
                lib_name = lib_entry.name_ge if lib_entry else '?'
                conf = m.get('match_confidence', '')
                sim = m.get('similarity', 0)
                print(f'  {i+1:2}. {"✓":6} {it["name"]:40}  {conf:10}  sim={sim:.2f}  → {lib_name}')
                matched += 1
            else:
                print(f'  {i+1:2}. {"✗":6} {it["name"]:40}  NO MATCH')

        print()
        print(f'RESULT: {matched}/{len(items)} items matched with library photos')
        unmatched = [items[i]['name'] for i in range(len(items)) if i not in match_map]
        if unmatched:
            print(f'\nUNMATCHED ({len(unmatched)}):')
            for n in unmatched:
                print(f'  • {n}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python scripts/debug_import.py path/to/menu.jpg')
        sys.exit(1)
    main(sys.argv[1])
