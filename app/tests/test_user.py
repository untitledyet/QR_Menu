import unittest
from app import create_app, db
from app.models import User

class UserTestCase(unittest.TestCase):

    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_create_user(self):
        user = User(username='testuser', email='test@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()

        self.assertIsNotNone(user.id)
        self.assertTrue(user.check_password('password123'))
        self.assertEqual(user.username, 'testuser')
        self.assertEqual(user.email, 'test@example.com')

if __name__ == '__main__':
    unittest.main()
