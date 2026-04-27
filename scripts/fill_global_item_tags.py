"""Bulk-generate tags for all GlobalItems using GPT.

Processes items in batches of 15 (one GPT call per batch).
By default only fills items with empty tags. Use --all to regenerate everything.

Usage:
    python scripts/fill_global_item_tags.py [--all] [--dry-run]
"""
import os
import sys
import json
import argparse
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BATCH = 15

_SYSTEM = (
    'You are a culinary expert familiar with Georgian restaurant menus. '
    'Given a JSON list of dishes (id, name_ge, name_en), return a JSON object '
    'mapping each id (as a string key) to a comma-separated string of alias tags '
    'that a waiter, OCR scan, or customer might write on a printed menu.\n'
    'INCLUDE for each dish:\n'
    '• Word-order variants: "ყველის ხინKALi" ↔ "ხინKALi ყველის"\n'
    '• Parenthetical forms: "მეგRULi ხაჭაpური" → "ხაჭაpური (მეგRULi)"\n'
    '• Portion variants for dishes that commonly come in pieces '
    '(ხაჭაpური, ლობიანი, ლობიო, პელმენი, ხინKALi, etc.): '
    '"<name> (8 ნAჭRIANi)", "<name> (6 ნAჭRIANi)", '
    '"8 ნAჭRIANi <name>", "6 ნAჭRIANi <name>"\n'
    '• Shortened / informal forms and common alternate spellings\n'
    '• English transliterations and standard English culinary names\n'
    'DO NOT repeat the canonical name_ge or name_en themselves.\n'
    'DO NOT include other dishes that are merely similar.\n'
    'Return ONLY valid JSON: {"<id>": "tag1, tag2, tag3", ...}'
)


def generate_tags_batch(items: list, client) -> dict:
    """Returns {id: tags_string} for the given batch."""
    payload = [{'id': str(it.id), 'name_ge': it.name_ge or '', 'name_en': it.name_en or ''} for it in items]
    try:
        resp = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {'role': 'system', 'content': _SYSTEM},
                {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=2000,
            response_format={'type': 'json_object'},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f'  [!] batch error: {e}')
        return {}


def main(regen_all: bool, dry_run: bool):
    from app import create_app
    from app.models import db, GlobalItem
    from openai import OpenAI

    app = create_app()
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

    with app.app_context():
        if regen_all:
            items = GlobalItem.query.order_by(GlobalItem.name_ge).all()
        else:
            items = GlobalItem.query.filter(
                db.or_(GlobalItem.tags == None, GlobalItem.tags == '')
            ).order_by(GlobalItem.name_ge).all()

        print(f'Items to process: {len(items)}')
        if not items:
            print('Nothing to do.')
            return

        total_updated = 0
        for i in range(0, len(items), BATCH):
            batch = items[i:i + BATCH]
            print(f'  Batch {i // BATCH + 1}/{-(-len(items) // BATCH)}  ({len(batch)} items)...', end=' ', flush=True)

            result = generate_tags_batch(batch, client)
            if not result:
                print('skipped (error)')
                continue

            updated = 0
            for it in batch:
                tags = result.get(str(it.id), '').strip()
                if not tags:
                    continue
                if not dry_run:
                    it.tags = tags
                updated += 1

            if not dry_run:
                db.session.commit()

            total_updated += updated
            print(f'tagged {updated}/{len(batch)}')

            # Show sample
            for it in batch[:3]:
                t = result.get(str(it.id), '')
                if t:
                    print(f'    [{it.id}] {it.name_ge}: {t[:90]}')

        suffix = ' [DRY RUN]' if dry_run else ''
        print(f'\nDone. {total_updated} items tagged.{suffix}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', dest='regen_all', action='store_true', help='Regenerate tags for all items, not just empty ones')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    main(regen_all=args.regen_all, dry_run=args.dry_run)
