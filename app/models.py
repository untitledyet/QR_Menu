from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from app import db

class User(db.Model):  # User მოდელი
    __tablename__ = 'Users'

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<User Table {self.id}>"

class Category(db.Model):
    __tablename__ = 'Categories'

    CategoryID = db.Column(db.Integer, primary_key=True)
    CategoryName = db.Column(db.String(50), nullable=False)
    Description = db.Column(db.String(200), nullable=True)
    CategoryIcon = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f"<Category {self.CategoryName}>"

class Subcategory(db.Model):
    __tablename__ = 'Subcategories'

    SubcategoryID = db.Column(db.Integer, primary_key=True)
    SubcategoryName = db.Column(db.String(50), nullable=False)
    CategoryID = db.Column(db.Integer, db.ForeignKey('Categories.CategoryID'), nullable=False)
    category = db.relationship('Category', backref=db.backref('subcategories', lazy=True))

    def __repr__(self):
        return f"<Subcategory {self.SubcategoryName}>"

class FoodItem(db.Model):
    __tablename__ = 'FoodItems'

    FoodItemID = db.Column(db.Integer, primary_key=True)
    FoodName = db.Column(db.String(50), nullable=False)
    Description = db.Column(db.String(200), nullable=False)
    Ingredients = db.Column(db.String(200), nullable=False)
    Price = db.Column(db.Float, nullable=False)
    ImageFilename = db.Column(db.String(100), nullable=True)
    CategoryID = db.Column(db.Integer, db.ForeignKey('Categories.CategoryID'), nullable=False)
    SubcategoryID = db.Column(db.Integer, db.ForeignKey('Subcategories.SubcategoryID'), nullable=True)
    # ამოვიღეთ PromotionID, რადგან ის არ არის მონაცემთა ბაზაში


    def __repr__(self):
        return f"<FoodItem {self.FoodName}>"

    def to_dict(self):
        return {
            'FoodItemID': self.FoodItemID,
            'FoodName': self.FoodName,
            'Description': self.Description,
            'Ingredients': self.Ingredients,
            'Price': self.Price,
            'ImageFilename': self.ImageFilename,
            'CategoryID': self.CategoryID,
            'SubcategoryID': self.SubcategoryID,
            #'PromotionID': self.PromotionID
        }

class Promotion(db.Model):
    __tablename__ = 'Promotions'

    PromotionID = db.Column(db.Integer, primary_key=True)
    PromotionName = db.Column(db.String(100), nullable=False)
    Description = db.Column(db.String(255), nullable=True)
    Discount = db.Column(db.Float, nullable=True)
    StartDate = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    EndDate = db.Column(db.Date, nullable=False)
    BackgroundImage = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Promotion {self.PromotionName}>"

class Order(db.Model):
    __tablename__ = 'Orders'

    OrderID = db.Column(db.Integer, primary_key=True)
    TableID = db.Column(db.Integer, db.ForeignKey('Users.id'), nullable=False)  # დაკავშირება User მოდელთან
    Items = db.Column(db.Text, nullable=False)
    Status = db.Column(db.String(50), default="Pending")
    CreatedAt = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, TableID, Items):
        self.TableID = TableID
        self.Items = Items

    def __repr__(self):
        return f"<Order {self.OrderID} - Table {self.TableID}>"

class Ingredient(db.Model):
    __tablename__ = 'Ingredients'

    IngredientID = db.Column(db.Integer, primary_key=True)
    IngredientName = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"<Ingredient {self.IngredientName}>"
