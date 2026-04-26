"""One-time deduplication script for GlobalItems.

Finds generic items (e.g. "ხაჭაპური", "მწვადი") that are aliases of more
specific items ("იმერული ხაჭაპური", "ღორის მწვადი"), moves their names into
the specific item's tags, then deletes the generic.

Usage:
    cd /path/to/project
    python scripts/dedup_global_items.py [--dry-run]
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(dry_run: bool):
    from app import create_app
    from app.models import db, GlobalItem
    from openai import OpenAI

    app = create_app()
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

    with app.app_context():
        items = GlobalItem.query.order_by(GlobalItem.name_ge).all()
        names = [{'id': it.id, 'name': it.name_ge} for it in items]

        print(f'Found {len(items)} GlobalItems. Asking GPT to identify duplicates...\n')

        prompt = json.dumps(names, ensure_ascii=False)
        resp = client.chat.completions.create(
            model='gpt-4o',
            messages=[
                {'role': 'system', 'content': (
                    'You are given a JSON list of dish names with IDs from a restaurant menu database. '
                    'Identify items where one name is a generic/shortened version of a more specific item. '
                    'Example: "ხაჭაპური" is generic for "იმერული ხაჭაპური"; "მწვადი" is generic for "ღორის მწვადი" and "ხბოს მწვადი". '
                    'For each generic item, return which specific items it should become a tag of. '
                    'Rules: '
                    '1. Only mark as generic if there is a clearly more specific item in the list. '
                    '2. A generic can map to multiple specific items (it becomes a tag on all of them). '
                    '3. If two items are equally specific and just duplicates, keep the one with the fuller name. '
                    '4. Never merge genuinely different dishes. '
                    'Return ONLY valid JSON: '
                    '{"merges": [{"generic_id": 1, "generic_name": "...", "keep_ids": [2, 3]}]}'
                )},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.0,
            max_tokens=1000,
            response_format={'type': 'json_object'},
        )

        result = json.loads(resp.choices[0].message.content)
        merges = result.get('merges', [])

        if not merges:
            print('✅ No duplicates found.')
            return

        id_map = {it.id: it for it in items}

        print('── Planned changes ──────────────────────────────────')
        for m in merges:
            gid = m['generic_id']
            gname = m['generic_name']
            keep_ids = m['keep_ids']
            keep_names = [id_map[k].name_ge for k in keep_ids if k in id_map]
            print(f'  DELETE  #{gid} "{gname}"')
            for kname in keep_names:
                print(f'  TAG ADD "{gname}" → "{kname}"')
        print('─────────────────────────────────────────────────────')

        if dry_run:
            print('\n[dry-run] No changes made.')
            return

        confirm = input('\nExecute? (yes/no): ').strip().lower()
        if confirm != 'yes':
            print('Aborted.')
            return

        for m in merges:
            gid = m['generic_id']
            gname = m['generic_name']
            keep_ids = m['keep_ids']

            for kid in keep_ids:
                target = id_map.get(kid)
                if not target:
                    continue
                existing = [t.strip() for t in (target.tags or '').split(',') if t.strip()]
                if gname.lower() not in [t.lower() for t in existing]:
                    existing.append(gname)
                target.tags = ', '.join(existing)

            generic = id_map.get(gid)
            if generic:
                db.session.delete(generic)
                print(f'  ✅ Deleted #{gid} "{gname}", tag added to {keep_ids}')

        db.session.commit()
        print('\nDone.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Preview only, no DB changes')
    args = parser.parse_args()
    main(dry_run=args.dry_run)
