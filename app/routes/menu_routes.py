from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify, current_app
from app.models import FoodItem, Category, Subcategory, Promotion

menu_bp = Blueprint('menu_bp', __name__)


@menu_bp.route('/table/<int:table_id>')
def home(table_id):
    session['table_id'] = table_id

    # ჩაწერე FEATURE_FLAGS session-ში
    session['FEATURE_FLAGS'] = current_app.config['FEATURE_FLAGS']

    categories = Category.query.all()
    promotions = Promotion.query.all()  # პრომოუშენების დამატება
    popular_dishes = [dish.to_dict() for dish in FoodItem.query.limit(6).all()]
    new_dishes = [dish.to_dict() for dish in FoodItem.query.order_by(FoodItem.FoodItemID.desc()).limit(9).all()]

    return render_template('index.html',
                           categories=categories,
                           promotions=promotions,
                           popular_dishes=popular_dishes,
                           new_dishes=new_dishes,
                           table_id=table_id)


@menu_bp.route('/table/<int:table_id>/cart')
def cart_page(table_id):
    print("Session FEATURE_FLAGS:", session.get('FEATURE_FLAGS'))
    if session.get('table_id') != table_id:
        flash('Table ID does not match session.')
        return redirect(url_for('menu_bp.home', table_id=table_id))

    if not session.get('FEATURE_FLAGS', {}).get('enable_cart_functionality', False):
        flash('Cart functionality is not available for your account type.')
        return redirect(url_for('menu_bp.home', table_id=table_id))

    return render_template('cart.html', table_id=table_id)


@menu_bp.route('/category/<int:category_id>')
def get_items_by_category(category_id):
    items = FoodItem.query.filter_by(CategoryID=category_id).all()
    subcategories = Subcategory.query.filter_by(CategoryID=category_id).all()
    items_data = [
        {
            'FoodName': item.FoodName,
            'Ingredients': item.Ingredients,
            'Description': item.Description,
            'Price': item.Price,
            'ImageFilename': item.ImageFilename,
            'SubcategoryID': item.SubcategoryID,
        }
        for item in items
    ]
    subcategories_data = [
        {
            'SubcategoryID': sub.SubcategoryID,
            'SubcategoryName': sub.SubcategoryName
        }
        for sub in subcategories
    ]
    return jsonify(items=items_data, subcategories=subcategories_data)


@menu_bp.route('/subcategory/<int:subcategory_id>')
def get_items_by_subcategory(subcategory_id):
    items = FoodItem.query.filter_by(SubcategoryID=subcategory_id).all()
    items_data = [
        {
            'FoodName': item.FoodName,
            'Ingredients': item.Ingredients,
            'Description': item.Description,
            'Price': item.Price,
            'ImageFilename': item.ImageFilename,
        }
        for item in items
    ]
    return jsonify(items=items_data)


@menu_bp.route('/table/<int:table_id>/item/<int:item_id>')
def get_item_detail(table_id, item_id):
    item = FoodItem.query.get_or_404(item_id).to_dict()
    return jsonify(item)


@menu_bp.route('/promotion/<int:promotion_id>')
def promotion_detail(promotion_id):
    promotion = Promotion.query.get_or_404(promotion_id)
    return render_template('promotion_detail.html', promotion=promotion)


@menu_bp.route('/order', methods=['POST'])
def place_order():
    table_id = session.get('table_id')
    if not table_id:
        return redirect(url_for('menu_bp.home', table_id=table_id))

    # Order processing logic goes here

    return jsonify({'status': 'Order placed successfully', 'table_id': table_id})
