from flask import Blueprint, render_template, session, redirect, url_for, flash, jsonify
from app.models import FoodItem, Category, Subcategory

menu_bp = Blueprint('menu_bp', __name__)

@menu_bp.route('/table/<int:table_id>')
def home(table_id):
    session['table_id'] = table_id

    categories = Category.query.all()
    popular_dishes = [dish.to_dict() for dish in FoodItem.query.limit(6).all()]  # ობიექტების სერიალიზაცია
    new_dishes = [dish.to_dict() for dish in FoodItem.query.order_by(FoodItem.FoodItemID.desc()).limit(9).all()]

    return render_template('index.html',
                           categories=categories,
                           popular_dishes=popular_dishes,
                           new_dishes=new_dishes,
                           table_id=table_id)

@menu_bp.route('/table/<int:table_id>/cart')
def cart_page(table_id):
    if session.get('table_id') != table_id:
        flash('Table ID does not match session.')
        return redirect(url_for('menu_bp.home', table_id=table_id))

    if not session.get('FEATURE_FLAGS', {}).get('enable_cart_functionality', False):
        flash('Cart functionality is not available for your account type.')
        return redirect(url_for('menu_bp.home', table_id=table_id))

    return render_template('cart.html', table_id=table_id)

@menu_bp.route('/table/<int:table_id>/category/<int:category_id>')
def get_items_by_category(table_id, category_id):
    items = [item.to_dict() for item in FoodItem.query.filter_by(CategoryID=category_id).all()]
    subcategories = [subcategory.to_dict() for subcategory in Subcategory.query.filter_by(CategoryID=category_id).all()]

    return jsonify({
        'items': items,
        'subcategories': subcategories
    })

@menu_bp.route('/table/<int:table_id>/item/<int:item_id>')
def get_item_detail(table_id, item_id):
    item = FoodItem.query.get_or_404(item_id).to_dict()
    return jsonify(item)

