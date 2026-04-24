from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify, abort
from sqlalchemy.orm import selectinload
from app import db
from app.models import FoodItem, Category, Subcategory, Promotion, Venue, VenueItemPriceOverride

menu_bp = Blueprint('menu_bp', __name__)


def _apply_price_override(item, price_overrides):
    """Return item.to_dict() with price replaced by branch override if present."""
    d = item.to_dict()
    if item.FoodItemID in price_overrides:
        d['Price'] = price_overrides[item.FoodItemID]
    return d


def get_venue_or_404(slug):
    venue = Venue.query.filter_by(slug=slug, is_active=True).first()
    if not venue:
        abort(404)
    return venue


def validate_table_id(venue, table_id):
    """Check that table_id is within the venue's configured total_tables range."""
    total = venue.total_tables or 0
    if total > 0 and (table_id < 1 or table_id > total):
        return False, total
    return True, total


def _load_price_overrides(venue):
    """Return {food_item_id: price} for this venue's branch overrides (empty if standalone)."""
    if not venue.group_id:
        return {}
    rows = VenueItemPriceOverride.query.filter_by(venue_id=venue.id).all()
    return {ov.food_item_id: ov.price for ov in rows}


def _load_all_categories(venue):
    """Fetch venue-local + group-shared categories with subcategories eager-loaded.

    Returns (all_categories, group_categories) where all_categories is ordered
    with group categories first (matching the original render contract).
    """
    local = (
        Category.query
        .options(selectinload(Category.subcategories))
        .filter_by(venue_id=venue.id)
        .all()
    )
    group = []
    if venue.group_id:
        group = (
            Category.query
            .options(selectinload(Category.subcategories))
            .filter_by(group_id=venue.group_id, venue_id=None)
            .all()
        )
    return group + local, group


@menu_bp.route('/<slug>/table/<int:table_id>')
def home(slug, table_id):
    venue = get_venue_or_404(slug)

    valid, total = validate_table_id(venue, table_id)
    if not valid:
        return render_template('table_error.html', venue=venue, table_id=table_id, total_tables=total), 404

    session['table_id'] = table_id
    session['venue_slug'] = slug
    session['venue_id'] = venue.id

    features = venue.get_all_features()
    session['features'] = features

    all_categories, group_categories = _load_all_categories(venue)
    price_overrides = _load_price_overrides(venue)

    promotions = (
        Promotion.query.filter_by(venue_id=venue.id, is_active=True).all()
        if features.get('promotions') else []
    )

    # Single query for popular + new dishes (we fetch the superset once, split in Python)
    all_cat_ids = [c.CategoryID for c in all_categories]
    if all_cat_ids:
        recent_items = (
            FoodItem.query
            .filter(FoodItem.CategoryID.in_(all_cat_ids), FoodItem.is_active == True)
            .order_by(FoodItem.FoodItemID.desc())
            .limit(9)
            .all()
        )
    else:
        recent_items = []

    new_dishes = [_apply_price_override(d, price_overrides) for d in recent_items]
    popular_dishes = new_dishes[:6]

    return render_template(
        'index.html',
        venue=venue, categories=all_categories,
        group_categories=group_categories,
        promotions=promotions,
        popular_dishes=popular_dishes, new_dishes=new_dishes,
        table_id=table_id, features=features,
        price_overrides=price_overrides,
    )


@menu_bp.route('/<slug>/table/<int:table_id>/cart')
def cart_page(slug, table_id):
    venue = get_venue_or_404(slug)

    valid, total = validate_table_id(venue, table_id)
    if not valid:
        return render_template('table_error.html', venue=venue, table_id=table_id, total_tables=total), 404

    features = venue.get_all_features()

    session['table_id'] = table_id
    session['venue_slug'] = slug
    session['venue_id'] = venue.id

    if not features.get('cart'):
        flash('Cart is not available.')
        return redirect(url_for('menu_bp.home', slug=slug, table_id=table_id))

    return render_template('cart.html', venue=venue, table_id=table_id, features=features)


@menu_bp.route('/<slug>/category/<int:category_id>')
def get_items_by_category(slug, category_id):
    venue = get_venue_or_404(slug)

    # Category may belong to the venue directly OR to the venue's group
    cat = Category.query.filter_by(CategoryID=category_id, venue_id=venue.id).first()
    if not cat and venue.group_id:
        cat = Category.query.filter_by(
            CategoryID=category_id, group_id=venue.group_id, venue_id=None
        ).first()
    if not cat:
        abort(404)

    price_overrides = _load_price_overrides(venue)

    items = FoodItem.query.filter_by(CategoryID=category_id, is_active=True).all()
    subcategories = Subcategory.query.filter_by(CategoryID=category_id).all()

    return jsonify(
        items=[{
            'FoodName': i.FoodName, 'FoodName_en': i.FoodName_en or '',
            'Ingredients': i.Ingredients, 'Ingredients_en': i.Ingredients_en or '',
            'Description': i.Description, 'Description_en': i.Description_en or '',
            'Price': price_overrides.get(i.FoodItemID, i.Price),
            'ImageFilename': i.ImageFilename, 'SubcategoryID': i.SubcategoryID,
            'FoodItemID': i.FoodItemID, 'AllowCustomization': i.allow_customization,
        } for i in items],
        subcategories=[{
            'SubcategoryID': s.SubcategoryID,
            'SubcategoryName': s.SubcategoryName,
            'SubcategoryName_en': s.SubcategoryName_en or '',
        } for s in subcategories]
    )


@menu_bp.route('/<slug>/subcategory/<int:subcategory_id>')
def get_items_by_subcategory(slug, subcategory_id):
    venue = get_venue_or_404(slug)
    price_overrides = _load_price_overrides(venue)
    items = FoodItem.query.filter_by(SubcategoryID=subcategory_id, is_active=True).all()

    return jsonify(items=[{
        'FoodName': i.FoodName, 'FoodName_en': i.FoodName_en or '',
        'Ingredients': i.Ingredients, 'Ingredients_en': i.Ingredients_en or '',
        'Description': i.Description, 'Description_en': i.Description_en or '',
        'Price': price_overrides.get(i.FoodItemID, i.Price),
        'ImageFilename': i.ImageFilename,
        'FoodItemID': i.FoodItemID, 'AllowCustomization': i.allow_customization,
    } for i in items])


@menu_bp.route('/<slug>/promotion/<int:promotion_id>')
def promotion_detail(slug, promotion_id):
    venue = get_venue_or_404(slug)
    promotion = Promotion.query.filter_by(PromotionID=promotion_id, venue_id=venue.id).first_or_404()
    return render_template('promotion_detail.html', promotion=promotion)


@menu_bp.route('/<slug>/order', methods=['POST'])
def place_order(slug):
    venue = get_venue_or_404(slug)
    table_id = session.get('table_id')
    if not table_id:
        return redirect(url_for('menu_bp.home', slug=slug, table_id=1))
    return jsonify({'status': 'Order placed', 'table_id': table_id, 'venue': venue.name})


@menu_bp.route('/<slug>/reservations')
def reservations_page(slug):
    venue = get_venue_or_404(slug)
    if not venue.has_feature('reservations'):
        abort(404)
    return render_template('reservation.html', venue=venue)
