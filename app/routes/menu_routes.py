from flask import render_template, jsonify, request
from app import app
from app.models.models import FoodItem, Category, Subcategory, Promotion

@app.route('/')
def home():
    categories = Category.query.all()
    promotions = Promotion.query.all()
    popular_dishes = [dish.to_dict() for dish in FoodItem.query.limit(6).all()]
    new_dishes = [dish.to_dict() for dish in FoodItem.query.order_by(FoodItem.FoodItemID.desc()).limit(6).all()]
    return render_template('index.html', categories=categories, promotions=promotions, popular_dishes=popular_dishes, new_dishes=new_dishes)

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
