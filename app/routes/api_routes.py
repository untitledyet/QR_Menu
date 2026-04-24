from flask import Blueprint, jsonify
from app.models import FoodItem, Category, Venue

api_bp = Blueprint('api_bp', __name__)


@api_bp.route('/api/<slug>/items')
def get_items(slug):
    venue = Venue.query.filter_by(slug=slug, is_active=True).first_or_404()
    items = FoodItem.query.filter(
        FoodItem.CategoryID.in_([c.CategoryID for c in venue.categories]),
        FoodItem.is_active == True
    ).all()
    return jsonify([item.to_dict() for item in items])
