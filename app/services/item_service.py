from app.models import FoodItem

class ItemService:
    @staticmethod
    def get_item_by_id(item_id):
        return FoodItem.query.get(item_id)

    @staticmethod
    def get_items_by_category(category_id):
        return FoodItem.query.filter_by(CategoryID=category_id).all()

    @staticmethod
    def get_items_by_subcategory(subcategory_id):
        return FoodItem.query.filter_by(SubcategoryID=subcategory_id).all()

    @staticmethod
    def get_popular_items(limit=6):
        return FoodItem.query.limit(limit).all()

    @staticmethod
    def get_new_items(limit=9):
        return FoodItem.query.order_by(FoodItem.FoodItemID.desc()).limit(limit).all()
