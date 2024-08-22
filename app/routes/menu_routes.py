from flask import render_template, jsonify, request, session, redirect, url_for
from app import app
from app.models.models import FoodItem, Category, Subcategory, Promotion

@app.route('/table/<int:table_id>')
def home(table_id):
    # Save the table ID in the session
    session['table_id'] = table_id

    categories = Category.query.all()
    promotions = Promotion.query.all()
    popular_dishes = [dish.to_dict() for dish in FoodItem.query.limit(6).all()]
    new_dishes = [dish.to_dict() for dish in FoodItem.query.order_by(FoodItem.FoodItemID.desc()).limit(9).all()]

    return render_template('index.html', categories=categories, promotions=promotions, popular_dishes=popular_dishes, new_dishes=new_dishes)

@app.route('/order', methods=['POST'])
def place_order():
    table_id = session.get('table_id')
    if not table_id:
        return redirect(url_for('home'))

    # Process the order based on the table_id
    # order processing code here

    return jsonify({'status': 'Order placed successfully', 'table_id': table_id})
@app.route('/category/<int:category_id>')
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

@app.route('/subcategory/<int:subcategory_id>')
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

@app.route('/promotion/<int:promotion_id>')
def promotion_detail(promotion_id):
    promotion = Promotion.query.get_or_404(promotion_id)
    return render_template('promotion_detail.html', promotion=promotion)


@app.route('/table/<int:table_id>/cart')
def cart_page(table_id):
    # საჭიროებისამებრ, დაამატეთ ლოგიკა table_id-ისთვის
    return render_template('cart.html', table_id=table_id)

