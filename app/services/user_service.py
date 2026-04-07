from app import db
from app.models import User


class UserService:
    @staticmethod
    def get_user_by_id(user_id):
        return User.query.get(user_id)

    @staticmethod
    def create_user():
        """Create a new user (table session)."""
        user = User()
        db.session.add(user)
        db.session.commit()
        return user
