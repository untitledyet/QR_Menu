"""
One-time migration: copy Paulaner (venue_id=1) menu into GlobalLibrary.
Run once on production after deploy:
  python migrate_to_library.py
"""
from app import create_app, db
from app.models import Category, Subcategory, FoodItem, GlobalCategory, GlobalItem

app = create_app()

with app.app_context():
    # Check if already migrated
    if GlobalCategory.query.count() > 0:
        print("GlobalLibrary already has data — skipping migration.")
        exit(0)

    # Get Paulaner venue categories (venue_id=1)
    categories = Category.query.filter_by(venue_id=1).all()
    if not categories:
        print("No categories found for venue_id=1 — nothing to migrate.")
        exit(0)

    print(f"Migrating {len(categories)} categories from Paulaner to GlobalLibrary...")

    cat_map = {}  # old CategoryID -> new GlobalCategory.id

    for cat in categories:
        global_cat = GlobalCategory(
            name=cat.CategoryName,
            description=cat.Description or '',
            icon=cat.CategoryIcon,
            sort_order=0,
            is_active=True,
        )
        db.session.add(global_cat)
        db.session.flush()
        cat_map[cat.CategoryID] = global_cat.id
        print(f"  Category: {cat.CategoryName} -> GlobalCategory #{global_cat.id}")

    # Migrate items
    item_count = 0
    for old_cat_id, new_cat_id in cat_map.items():
        items = FoodItem.query.filter_by(CategoryID=old_cat_id).all()
        for item in items:
            global_item = GlobalItem(
                category_id=new_cat_id,
                name=item.FoodName,
                description=item.Description or '',
                ingredients=item.Ingredients or '',
                image_filename=item.ImageFilename,
                is_active=True,
            )
            db.session.add(global_item)
            item_count += 1

    db.session.commit()
    print(f"\nMigration complete: {len(cat_map)} categories, {item_count} items copied to GlobalLibrary.")
    print("Paulaner's original menu is unchanged — still linked to venue_id=1.")
