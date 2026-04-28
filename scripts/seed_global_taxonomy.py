"""Seed GlobalCategories and GlobalSubcategories with the standard Georgian restaurant taxonomy.

Run from project root:
    flask shell < scripts/seed_global_taxonomy.py
or:
    python scripts/seed_global_taxonomy.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import GlobalCategory, GlobalSubcategory

TAXONOMY = [
    {
        "name": "ცხელი კერძები", "name_en": "Hot Dishes",
        "icon": "fa-fire", "sort_order": 1,
        "subs": [
            ("ხინკალი", "Khinkali", 1),
            ("მცხვადი", "Mtsvadi / BBQ", 2),
            ("ქათამი", "Chicken", 3),
            ("ღორი", "Pork", 4),
            ("ხბო / საქონელი", "Veal / Beef", 5),
            ("კერძები ქვაბში", "Pottery Dishes", 6),
            ("ფილე და სტეიქი", "Steaks & Fillets", 7),
        ],
    },
    {
        "name": "ცომეული", "name_en": "Bread & Pastries",
        "icon": "fa-bread-slice", "sort_order": 2,
        "subs": [
            ("ხაჭაპური", "Khachapuri", 1),
            ("ლობიანი", "Lobiani", 2),
            ("მჭადი", "Mchadi", 3),
            ("პური", "Bread", 4),
            ("სხვა ცომეული", "Other Pastries", 5),
        ],
    },
    {
        "name": "სუპები", "name_en": "Soups",
        "icon": "fa-bowl-food", "sort_order": 3,
        "subs": [
            ("ხარჩო", "Kharcho", 1),
            ("ჩიხირთმა", "Chikhirtma", 2),
            ("ბორში", "Borsch", 3),
            ("ცივი სუპი", "Cold Soups", 4),
            ("სხვა სუპები", "Other Soups", 5),
        ],
    },
    {
        "name": "სალათები", "name_en": "Salads",
        "icon": "fa-leaf", "sort_order": 4,
        "subs": [
            ("ქართული სალათი", "Georgian Salad", 1),
            ("სეზონური სალათი", "Seasonal Salad", 2),
            ("პრემიუმ სალათი", "Premium Salad", 3),
            ("ცხელი სალათი", "Warm Salad", 4),
        ],
    },
    {
        "name": "ცივი კერძები და წახემსები", "name_en": "Cold Dishes & Appetizers",
        "icon": "fa-utensils", "sort_order": 5,
        "subs": [
            ("ფხალი", "Pkhali", 1),
            ("ბადრიჯანი", "Eggplant Rolls", 2),
            ("ყველის ასორტი", "Cheese Platter", 3),
            ("კარპაჩო / ტარტარი", "Carpaccio / Tartare", 4),
            ("სხვა წახემსები", "Other Appetizers", 5),
        ],
    },
    {
        "name": "პასტა და რიზოტო", "name_en": "Pasta & Risotto",
        "icon": "fa-bowl-rice", "sort_order": 6,
        "subs": [
            ("პასტა", "Pasta", 1),
            ("რიზოტო", "Risotto", 2),
            ("ლაზანია", "Lasagna", 3),
        ],
    },
    {
        "name": "პიცა", "name_en": "Pizza",
        "icon": "fa-pizza-slice", "sort_order": 7,
        "subs": [
            ("კლასიკური პიცა", "Classic Pizza", 1),
            ("სპეციალური პიცა", "Specialty Pizza", 2),
        ],
    },
    {
        "name": "ბერგერი და სენდვიჩი", "name_en": "Burgers & Sandwiches",
        "icon": "fa-burger", "sort_order": 8,
        "subs": [
            ("ბერგერი", "Burgers", 1),
            ("სენდვიჩი", "Sandwiches", 2),
            ("შაურმა", "Shaurma", 3),
            ("ჰოთ-დოგი", "Hot Dogs", 4),
        ],
    },
    {
        "name": "სუშები და აზიური", "name_en": "Sushi & Asian",
        "icon": "fa-fish", "sort_order": 9,
        "subs": [
            ("სუშები", "Sushi", 1),
            ("როლი", "Rolls", 2),
            ("სხვა აზიური", "Other Asian", 3),
        ],
    },
    {
        "name": "დესერტი", "name_en": "Desserts",
        "icon": "fa-cake-candles", "sort_order": 10,
        "subs": [
            ("ნაყინი", "Ice Cream", 1),
            ("ნამცხვარი", "Cakes", 2),
            ("ქართული ტრადიციული", "Traditional Georgian", 3),
            ("ცომეული დესერტი", "Pastry Desserts", 4),
        ],
    },
    {
        "name": "სასმელი", "name_en": "Drinks",
        "icon": "fa-glass-water", "sort_order": 11,
        "subs": [
            ("წყალი", "Water", 1),
            ("ლიმონათი და სოფტ დრინქი", "Lemonades & Soft Drinks", 2),
            ("წვენი ფრეში", "Fresh Juice", 3),
            ("ყავა", "Coffee", 4),
            ("ჩაი", "Tea", 5),
            ("სხვა ცხელი სასმელი", "Other Hot Drinks", 6),
        ],
    },
    {
        "name": "ალკოჰოლი", "name_en": "Alcohol",
        "icon": "fa-wine-glass", "sort_order": 12,
        "subs": [
            ("ღვინო წითელი", "Red Wine", 1),
            ("ღვინო თეთრი", "White Wine", 2),
            ("ჭაჭა", "Chacha", 3),
            ("ლუდი", "Beer", 4),
            ("კოქტეილი", "Cocktails", 5),
            ("სხვა ალკოჰოლი", "Spirits", 6),
        ],
    },
    {
        "name": "ბავშვის მენიუ", "name_en": "Kids Menu",
        "icon": "fa-child", "sort_order": 13,
        "subs": [
            ("ბავშვის კერძები", "Kids Dishes", 1),
            ("ბავშვის სასმელი", "Kids Drinks", 2),
        ],
    },
    {
        "name": "სპეციალური", "name_en": "Specials",
        "icon": "fa-star", "sort_order": 14,
        "subs": [
            ("შეფის სპეციალი", "Chef's Special", 1),
            ("ვეგანური", "Vegan", 2),
            ("გლუტენ-ფრი", "Gluten-Free", 3),
        ],
    },
]


def seed():
    existing = GlobalCategory.query.count()
    if existing > 0:
        print(f"GlobalCategories already has {existing} rows — skipping seed.")
        print("Use --force to re-seed (will delete existing data).")
        return

    total_cats = 0
    total_subs = 0

    for cat_data in TAXONOMY:
        cat = GlobalCategory(
            name=cat_data["name"],
            name_en=cat_data["name_en"],
            icon=cat_data["icon"],
            sort_order=cat_data["sort_order"],
            is_active=True,
        )
        db.session.add(cat)
        db.session.flush()  # get cat.id

        for sub_name, sub_name_en, sub_order in cat_data["subs"]:
            sub = GlobalSubcategory(
                category_id=cat.id,
                name=sub_name,
                name_en=sub_name_en,
                sort_order=sub_order,
                is_active=True,
            )
            db.session.add(sub)
            total_subs += 1

        total_cats += 1
        print(f"  [{cat_data['sort_order']:2d}] {cat_data['name']} — {len(cat_data['subs'])} subs")

    db.session.commit()
    print(f"\nSeeded {total_cats} GlobalCategories and {total_subs} GlobalSubcategories.")


def force_reseed():
    print("Deleting existing GlobalCategories and GlobalSubcategories...")
    GlobalSubcategory.query.delete()
    GlobalCategory.query.delete()
    db.session.commit()
    seed()


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        if '--force' in sys.argv:
            force_reseed()
        else:
            seed()
