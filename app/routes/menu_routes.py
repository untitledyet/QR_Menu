from flask import render_template, jsonify, request
from app import app
from app.models.models import FoodItem, Category, Promotion

@app.route('/')
def home():
    categories = Category.query.all()
    promotions = Promotion.query.all()
    popular_dishes = FoodItem.query.limit(6).all()  # Adjust this as needed
    new_dishes = FoodItem.query.order_by(FoodItem.FoodItemID.desc()).limit(6).all()
    return render_template('home.html', categories=categories, promotions=promotions, popular_dishes=popular_dishes, new_dishes=new_dishes)

@app.route('/category/<int:category_id>')
def get_items_by_category(category_id):
    items = FoodItem.query.filter_by(CategoryID=category_id).all()
    items_data = [
        {
            'FoodName': item.FoodName,
            'Description': item.Description,
            'Price': item.Price,
            'ImageFilename': item.ImageFilename,
        }
        for item in items
    ]
    return jsonify(items_data)

@app.route('/popular-dishes')
def popular_dishes():
    items = FoodItem.query.limit(6).all()  # Adjust this as needed
    items_data = [
        {
            'FoodName': item.FoodName,
            'Description': item.Description,
            'Price': item.Price,
            'ImageFilename': item.ImageFilename,
        }
        for item in items
    ]
    return jsonify(items_data)
