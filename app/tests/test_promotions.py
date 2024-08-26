import unittest
from app import create_app, db
from app.models import Promotion

class PromotionTestCase(unittest.TestCase):

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_create_promotion(self):
        promotion = Promotion(name='Holiday Sale', discount=15.00)
        db.session.add(promotion)
        db.session.commit()

        self.assertIsNotNone(promotion.id)
        self.assertEqual(promotion.name, 'Holiday Sale')
        self.assertEqual(promotion.discount, 15.00)

if __name__ == '__main__':
    unittest.main()
