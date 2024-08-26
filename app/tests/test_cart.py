import unittest
from app import create_app, db
from app.models import User, FoodItem, Cart

class CartTestCase(unittest.TestCase):

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.user = User(username='testuser', email='test@example.com')
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_add_item_to_cart(self):
        food_item = FoodItem(name='Pizza', price=10.00, description='Delicious cheese pizza')
        db.session.add(food_item)
        db.session.commit()

        cart = Cart(user_id=self.user.id)
        cart.add_item(food_item.id, 1)
        db.session.add(cart)
        db.session.commit()

        self.assertEqual(len(cart.items), 1)
        self.assertEqual(cart.items[0].food_item_id, food_item.id)
        self.assertEqual(cart.items[0].quantity, 1)

    def test_remove_item_from_cart(self):
        food_item = FoodItem(name='Pizza', price=10.00, description='Delicious cheese pizza')
        db.session.add(food_item)
        db.session.commit()

        cart = Cart(user_id=self.user.id)
        cart.add_item(food_item.id, 1)
        db.session.add(cart)
        db.session.commit()

        cart.remove_item(food_item.id)
        db.session.add(cart)
        db.session.commit()

        self.assertEqual(len(cart.items), 0)

if __name__ == '__main__':
    unittest.main()
