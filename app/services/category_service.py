"""Category resolution service.

Provides a stable interface for fetching venue-visible categories and subcategories,
applying sort_order and is_hidden filtering.
"""
import openai
from sqlalchemy.orm import selectinload
from app import db
from app.models import Category, Subcategory, GlobalCategory, GlobalSubcategory
from app import config


# ---------------------------------------------------------------------------
# Venue type → list of global category names to pre-assign on onboarding
# ---------------------------------------------------------------------------

VENUE_TYPE_PRESETS: dict[str, list[str]] = {
    "restaurant": [
        "ცხელი კერძები", "ცომეული", "სუპები", "სალათები",
        "ცივი კერძები და წახემსები", "დესერტი", "სასმელი", "ალკოჰოლი",
    ],
    "cafe": [
        "სალათები", "ბერგერი და სენდვიჩი", "ცომეული", "დესერტი", "სასმელი",
    ],
    "bar": [
        "ცივი კერძები და წახემსები", "ბერგერი და სენდვიჩი",
        "ალკოჰოლი", "სასმელი",
    ],
    "fastfood": [
        "ბერგერი და სენდვიჩი", "პიცა", "სასმელი",
    ],
    "pizzeria": [
        "პიცა", "პასტა და რიზოტო", "სალათები", "სასმელი",
    ],
    "sushi": [
        "სუშები და აზიური", "სასმელი",
    ],
    "custom": [],
}

VENUE_TYPE_LABELS = {
    "restaurant": "რესტორანი",
    "cafe": "კაფე / ბრანჩი",
    "bar": "ბარი / პაბი",
    "fastfood": "ფასტ-ფუდი",
    "pizzeria": "პიცერია",
    "sushi": "სუშები",
    "custom": "ცარიელი (ხელით)",
}


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def get_venue_categories(venue_id: int, include_hidden: bool = False) -> list[Category]:
    """Return visible, sorted categories for a venue (local + group-shared)."""
    from app.models import Venue
    venue = Venue.query.get(venue_id)
    if not venue:
        return []

    conditions = [Category.venue_id == venue_id]
    if venue.group_id:
        conditions.append(
            db.and_(Category.group_id == venue.group_id, Category.venue_id.is_(None))
        )

    q = (
        Category.query
        .options(selectinload(Category.subcategories), selectinload(Category.global_category))
        .filter(db.or_(*conditions))
    )
    if not include_hidden:
        q = q.filter(Category.is_hidden == False)

    cats = q.all()
    cats.sort(key=lambda c: c.effective_sort_order)
    return cats


def get_visible_subcategories(category_id: int) -> list[Subcategory]:
    """Return visible, sorted subcategories for a category."""
    subs = (
        Subcategory.query
        .filter_by(CategoryID=category_id, is_hidden=False)
        .order_by(Subcategory.sort_order, Subcategory.SubcategoryID)
        .all()
    )
    return subs


# ---------------------------------------------------------------------------
# Onboarding — seed preset categories for a new venue
# ---------------------------------------------------------------------------

def seed_venue_categories(venue_id: int, venue_type: str) -> int:
    """Create Category rows for a venue based on venue_type preset.

    Returns the number of categories created.
    """
    preset_names = VENUE_TYPE_PRESETS.get(venue_type, [])
    if not preset_names:
        return 0

    global_cats = GlobalCategory.query.filter(
        GlobalCategory.name.in_(preset_names),
        GlobalCategory.is_active == True,
    ).all()
    global_by_name = {g.name: g for g in global_cats}

    existing_global_ids = {
        c.global_category_id
        for c in Category.query.filter_by(venue_id=venue_id).all()
        if c.global_category_id
    }

    created = 0
    for sort_idx, name in enumerate(preset_names, start=1):
        gc = global_by_name.get(name)
        if not gc:
            continue
        if gc.id in existing_global_ids:
            continue
        cat = Category(
            CategoryName=gc.name,
            CategoryName_en=gc.name_en,
            CategoryIcon=gc.icon,
            venue_id=venue_id,
            global_category_id=gc.id,
            sort_order=sort_idx,
            is_hidden=False,
        )
        db.session.add(cat)
        db.session.flush()
        seed_venue_subcategories(venue_id, cat.CategoryID, gc.id)
        created += 1

    if created:
        db.session.commit()
    return created


def seed_venue_subcategories(venue_id: int, category_id: int, global_category_id: int) -> int:
    """Create Subcategory rows for a venue category from global subcategory defaults."""
    global_subs = (
        GlobalSubcategory.query
        .filter_by(category_id=global_category_id, is_active=True)
        .order_by(GlobalSubcategory.sort_order)
        .all()
    )
    existing_global_sub_ids = {
        s.global_subcategory_id
        for s in Subcategory.query.filter_by(CategoryID=category_id).all()
        if s.global_subcategory_id
    }

    created = 0
    for gs in global_subs:
        if gs.id in existing_global_sub_ids:
            continue
        sub = Subcategory(
            SubcategoryName=gs.name,
            SubcategoryName_en=gs.name_en,
            CategoryID=category_id,
            global_subcategory_id=gs.id,
            sort_order=gs.sort_order,
            is_hidden=False,
        )
        db.session.add(sub)
        created += 1

    if created:
        db.session.commit()
    return created


# ---------------------------------------------------------------------------
# AI auto-translate category name
# ---------------------------------------------------------------------------

def ai_translate_category_name(name_ka: str) -> str | None:
    """Translate a category name from Georgian to English using OpenAI."""
    try:
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        resp = client.responses.create(
            model=config.OPENAI_MODEL_FAST,
            input=f"Translate this Georgian restaurant category name to English. "
                  f"Return only the translation, nothing else.\n\n{name_ka}",
        )
        return (resp.output_text or "").strip() or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Import helper — used by scraper to ensure venue has a Category row
# ---------------------------------------------------------------------------

def get_or_create_venue_category(
    venue_id: int,
    global_category_id: int | None,
    fallback_name: str,
    fallback_name_en: str | None = None,
) -> Category:
    """Return an existing Category for this venue+global_cat, or create one."""
    if global_category_id:
        existing = Category.query.filter_by(
            venue_id=venue_id, global_category_id=global_category_id
        ).first()
        if existing:
            return existing

    cat = Category(
        CategoryName=fallback_name,
        CategoryName_en=fallback_name_en,
        venue_id=venue_id,
        global_category_id=global_category_id,
        sort_order=0,
        is_hidden=False,
    )
    if global_category_id:
        gc = GlobalCategory.query.get(global_category_id)
        if gc:
            cat.CategoryIcon = gc.icon
            cat.sort_order = gc.sort_order
    db.session.add(cat)
    db.session.flush()
    return cat


def get_or_create_venue_subcategory(
    category_id: int,
    global_subcategory_id: int | None,
    fallback_name: str,
    fallback_name_en: str | None = None,
) -> Subcategory:
    """Return existing Subcategory for this category+global_sub, or create one."""
    if global_subcategory_id:
        existing = Subcategory.query.filter_by(
            CategoryID=category_id, global_subcategory_id=global_subcategory_id
        ).first()
        if existing:
            return existing

    sub = Subcategory(
        SubcategoryName=fallback_name,
        SubcategoryName_en=fallback_name_en,
        CategoryID=category_id,
        global_subcategory_id=global_subcategory_id,
        sort_order=0,
        is_hidden=False,
    )
    db.session.add(sub)
    db.session.flush()
    return sub
