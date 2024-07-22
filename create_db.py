from app import app, db
from app.models.models import MenuItem

with app.app_context():
    db.create_all()
