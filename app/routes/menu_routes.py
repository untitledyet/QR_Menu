from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify, abort
from app.models import FoodItem, Category, Subcategory, Promotion, Venue

menu_bp = Blueprint('menu_bp', __name__)


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

    categories = Category.query.filter_by(venue_id=venue.id).all()
    promotions = Promotion.query.filter_by(venue_id=venue.id, is_active=True).all() if features.get('promotions') else []
    popular_dishes = [d.to_dict() for d in FoodItem.query.filter(
        FoodItem.CategoryID.in_([c.CategoryID for c in categories]), FoodItem.is_active == True
    ).limit(6).all()]
    new_dishes = [d.to_dict() for d in FoodItem.query.filter(
        FoodItem.CategoryID.in_([c.CategoryID for c in categories]), FoodItem.is_active == True
    ).order_by(FoodItem.FoodItemID.desc()).limit(9).all()]

    return render_template('index.html',
                           venue=venue, categories=categories, promotions=promotions,
                           popular_dishes=popular_dishes, new_dishes=new_dishes,
                           table_id=table_id, features=features)


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
    # Ensure category belongs to this venue
    cat = Category.query.filter_by(CategoryID=category_id, venue_id=venue.id).first_or_404()
    items = FoodItem.query.filter_by(CategoryID=category_id, is_active=True).all()
    subcategories = Subcategory.query.filter_by(CategoryID=category_id).all()

    return jsonify(
        items=[{
            'FoodName': i.FoodName, 'Ingredients': i.Ingredients, 'Description': i.Description,
            'Price': i.Price, 'ImageFilename': i.ImageFilename, 'SubcategoryID': i.SubcategoryID,
            'FoodItemID': i.FoodItemID, 'AllowCustomization': i.allow_customization,
        } for i in items],
        subcategories=[{'SubcategoryID': s.SubcategoryID, 'SubcategoryName': s.SubcategoryName} for s in subcategories]
    )


@menu_bp.route('/<slug>/subcategory/<int:subcategory_id>')
def get_items_by_subcategory(slug, subcategory_id):
    venue = get_venue_or_404(slug)
    items = FoodItem.query.filter_by(SubcategoryID=subcategory_id, is_active=True).all()

    return jsonify(items=[{
        'FoodName': i.FoodName, 'Ingredients': i.Ingredients, 'Description': i.Description,
        'Price': i.Price, 'ImageFilename': i.ImageFilename,
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
