"""Retroactively assign library photos to FoodItems that have no image.

For each FoodItem with no photo:
  1. Normalize its name via batch GPT (strips quantities, fixes word order, etc.)
  2. Exact-match the normalized name against GlobalItem names + tags
  3. Assign the matching GlobalItem's image_filename

Usage:
    python scripts/assign_missing_photos.py [--dry-run]
"""
import os
import sys
import re
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BATCH = 50  # GPT calls per request


def normalize_batch(names: list, client) -> list:
    if not names:
        return names
    joined = '\n'.join(f'{i}. {n}' for i, n in enumerate(names))
    resp = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {'role': 'system', 'content': (
                'You are given a numbered list of restaurant dish names. '
                'For each, return the canonical dish name by applying these rules:\n'
                '1. Remove quantity/portion qualifiers: numbers, "ნაჭრიანი", "გრამიანი", "კგ", "გრ", "პორცია", "ნახევარი", "piece", "portion", "g", "kg".\n'
                '2. Remove size qualifiers: "დიდი", "პატარა", "მცირე", "საშუალო", "large", "small", "medium", "xl", "mini".\n'
                '3. Fix parenthetical reordering: "ხაჭაპური (აჭარული)" → "აჭარული ხაჭაპური".\n'
                '4. Fix word-order variants: "ხინკალი ქათმის" → "ქათმის ხინკალი".\n'
                '5. Preserve regional/ingredient qualifiers ("ღორის", "ხბოს", "იმერული", "მეგრული", "აჭარული").\n'
                'Return ONLY a numbered list in the exact same order. No explanation.'
            )},
            {'role': 'user', 'content': joined},
        ],
        temperature=0.0,
        max_tokens=1000,
    )
    lines = resp.choices[0].message.content.strip().split('\n')
    result = []
    for i, line in enumerate(lines):
        stripped = re.sub(r'^\d+\.\s*', '', line).strip()
        result.append(stripped if stripped else names[i])
    return result if len(result) == len(names) else names


def build_index(lib_items) -> dict:
    idx = {}
    for g in lib_items:
        if not g.image_filename:
            continue
        for key in [g.name_ge] + g.tags_list:
            if key:
                idx[key.strip().lower()] = g
    return idx


def main(dry_run: bool):
    from app import create_app
    from app.models import db, GlobalItem, FoodItem
    from openai import OpenAI

    app = create_app()
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

    with app.app_context():
        lib_items = GlobalItem.query.filter(GlobalItem.image_filename.isnot(None)).all()
        if not lib_items:
            print('No GlobalItems with photos found.')
            return

        tag_index = build_index(lib_items)
        print(f'Library index: {len(tag_index)} entries from {len(lib_items)} GlobalItems')

        food_items = FoodItem.query.filter(
            db.or_(
                FoodItem.ImageFilename == None,
                FoodItem.ImageFilename == '',
                FoodItem.ImageFilename == 'default-image.png',
            )
        ).all()
        print(f'FoodItems without photo: {len(food_items)}\n')

        if not food_items:
            print('Nothing to do.')
            return

        # Batch normalize
        all_names = [it.FoodName or '' for it in food_items]
        normalized = []
        for i in range(0, len(all_names), BATCH):
            batch = all_names[i:i + BATCH]
            print(f'  Normalizing batch {i // BATCH + 1}/{(len(all_names) - 1) // BATCH + 1}...')
            normalized.extend(normalize_batch(batch, client))

        # Match
        matches = []
        for item, norm in zip(food_items, normalized):
            key = norm.strip().lower()
            lib = tag_index.get(key)
            if lib:
                matches.append((item, lib, norm))

        print(f'\n── Matches found: {len(matches)} / {len(food_items)} ──────────────────')
        for item, lib, norm in matches:
            print(f'  "{item.FoodName}" → norm: "{norm}" → library: "{lib.name_ge}" → {lib.image_filename[:60]}...')

        no_match = [it for it, *_ in zip(food_items, normalized) if it not in [m[0] for m in matches]]
        if no_match:
            print(f'\n── No match ({len(no_match)}) ──────────────────────────────────')
            for it in no_match[:20]:
                print(f'  "{it.FoodName}"')
            if len(no_match) > 20:
                print(f'  ... and {len(no_match) - 20} more')

        if dry_run:
            print('\n[dry-run] No changes made.')
            return

        if not matches:
            print('\nNothing to assign.')
            return

        confirm = input(f'\nAssign photos to {len(matches)} items? (yes/no): ').strip().lower()
        if confirm != 'yes':
            print('Aborted.')
            return

        for item, lib, _ in matches:
            item.ImageFilename = lib.image_filename

        db.session.commit()
        print(f'\n✅ Done. {len(matches)} items updated.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
