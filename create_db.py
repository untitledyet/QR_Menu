from app import app, db
from app.models.models import Category, Subcategory, FoodItem, Ingredient, FoodItemPromotion, Promotion

with app.app_context():
    db.create_all()
