from flask import Blueprint, jsonify, request
from app.models import FoodItem, Category, Subcategory
from app import db

api_bp = Blueprint('api_bp', __name__)  # Blueprint-ის სახელის ცვლილება

@api_bp.route('/api/table/<int:table_id>/items', methods=['GET'])
def get_items(table_id):
    # table_id გამოიყენება ფილტრაციისთვის (მაგალითად, თუკი მაგიდა უკავშირდება კონკრეტულ კატეგორიას ან მომხმარებელს)
    items = FoodItem.query.filter_by(TableID=table_id).all()  # თუ TableID გამოიყენება, შეგიძლიათ დაამატოთ ფილტრაცია
    return jsonify([item.to_dict() for item in items])

# სხვა API როუტებიც ასევე შეიძლება იყოს დაკავშირებული table_id-სთან
