"""
One-time migration: copy Paulaner (venue_id=1) menu into GlobalLibrary.
Includes categories, subcategories, and items.
Run once on production after deploy:
  python migrate_to_library.py
"""
from app import create_app, db
from app.models import Category, Subcategory, FoodItem, GlobalCategory, GlobalSubcategory, GlobalItem

app = create_app()

with app.app_context():
    db.create_all()

    # Check if already migrated (items must exist)
    if GlobalItem.query.count() > 0:
        print("GlobalLibrary already has items — skipping migration.")
        exit(0)

    # Clean up any partial migration (categories without items)
    if GlobalCategory.query.count() > 0:
        print("Cleaning up partial migration...")
        GlobalItem.query.delete()
        GlobalSubcategory.query.delete()
        GlobalCategory.query.delete()
        db.session.commit()

    # Get Paulaner venue categories (venue_id=1)
    categories = Category.query.filter_by(venue_id=1).all()
    if not categories:
        print("No categories found for venue_id=1 — nothing to migrate.")
        exit(0)

    print(f"Migrating {len(categories)} categories from Paulaner to GlobalLibrary...")

    cat_map = {}       # old CategoryID -> new GlobalCategory.id
    subcat_map = {}    # old SubcategoryID -> new GlobalSubcategory.id

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

        # Migrate subcategories
        subcats = Subcategory.query.filter_by(CategoryID=cat.CategoryID).all()
        for sub in subcats:
            global_sub = GlobalSubcategory(
                category_id=global_cat.id,
                name=sub.SubcategoryName,
                is_active=True,
            )
            db.session.add(global_sub)
            db.session.flush()
            subcat_map[sub.SubcategoryID] = global_sub.id
            print(f"    Subcategory: {sub.SubcategoryName} -> GlobalSubcategory #{global_sub.id}")

    # Migrate items
    item_count = 0
    for old_cat_id, new_cat_id in cat_map.items():
        items = FoodItem.query.filter_by(CategoryID=old_cat_id).all()
        for item in items:
            new_sub_id = subcat_map.get(item.SubcategoryID) if item.SubcategoryID else None
            global_item = GlobalItem(
                category_id=new_cat_id,
                subcategory_id=new_sub_id,
                name=item.FoodName,
                description=item.Description or '',
                ingredients=item.Ingredients or '',
                image_filename=item.ImageFilename,
                is_active=True,
            )
            db.session.add(global_item)
            item_count += 1

    db.session.commit()
    print(f"\nMigration complete:")
    print(f"  {len(cat_map)} categories")
    print(f"  {len(subcat_map)} subcategories")
    print(f"  {item_count} items")
    print("Paulaner's original menu is unchanged.")
