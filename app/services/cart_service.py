import json

from app.models import FoodItem, Order
from app import db


class CartService:
    @staticmethod
    def add_item_to_cart(table_id, item_id, quantity=1):
        # Retrieve existing order for the table
        order = Order.query.filter_by(TableID=table_id, Status='Pending').first()

        if not order:
            # Create a new order if it doesn't exist
            order = Order(TableID=table_id, Items='[]')  # Initialize with empty list
            db.session.add(order)
            db.session.commit()

        # Add item to the order
        items = json.loads(order.Items)
        for item in items:
            if item['item_id'] == item_id:
                item['quantity'] += quantity
                break
        else:
            items.append({'item_id': item_id, 'quantity': quantity})

        order.Items = json.dumps(items)
        db.session.commit()

    @staticmethod
    def remove_item_from_cart(table_id, item_id):
        order = Order.query.filter_by(TableID=table_id, Status='Pending').first()
        if order:
            items = json.loads(order.Items)
            items = [item for item in items if item['item_id'] != item_id]
            order.Items = json.dumps(items)
            db.session.commit()

    @staticmethod
    def clear_cart(table_id):
        order = Order.query.filter_by(TableID=table_id, Status='Pending').first()
        if order:
            order.Items = '[]'
            db.session.commit()

    @staticmethod
    def get_cart_items(table_id):
        order = Order.query.filter_by(TableID=table_id, Status='Pending').first()
        if order:
            return json.loads(order.Items)
        return []
