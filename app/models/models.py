from app import db

class FoodItem(db.Model):
    __tablename__ = 'FoodItems'

    FoodItemID = db.Column(db.Integer, primary_key=True)
    FoodName = db.Column(db.String(50), nullable=False)
    Description = db.Column(db.String(200), nullable=False)
    Price = db.Column(db.Float, nullable=False)
    image_filename = db.Column(db.String(100), nullable=True)  # Filename of the image

    def __repr__(self):
        return f"FoodItem('{self.FoodName}', '{self.Price}')"
