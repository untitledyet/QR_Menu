import unittest
from app import create_app, db
from app.models import Category, FoodItem

class ItemTestCase(unittest.TestCase):

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_create_food_item(self):
        category = Category(name='Desserts', description='Sweet treats')
        db.session.add(category)
        db.session.commit()

        food_item = FoodItem(name='Ice Cream', price=5.00, description='Vanilla ice cream', category_id=category.id)
        db.session.add(food_item)
        db.session.commit()

        self.assertIsNotNone(food_item.id)
        self.assertEqual(food_item.name, 'Ice Cream')
        self.assertEqual(food_item.price, 5.00)

if __name__ == '__main__':
    unittest.main()
