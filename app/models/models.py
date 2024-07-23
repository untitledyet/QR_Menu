from app import db

class Category(db.Model):
    __tablename__ = 'Categories'

    CategoryID = db.Column(db.Integer, primary_key=True)
    CategoryName = db.Column(db.String(50), nullable=False)
    Description = db.Column(db.String(200), nullable=True)
    CategoryIcon = db.Column(db.String(100), nullable=True)  # New field for category icon

    def __repr__(self):
        return f"Category('{self.CategoryName}', '{self.CategoryIcon}')"


class Subcategory(db.Model):
    __tablename__ = 'Subcategories'

    SubcategoryID = db.Column(db.Integer, primary_key=True)
    SubcategoryName = db.Column(db.String(50), nullable=False)
    CategoryID = db.Column(db.Integer, db.ForeignKey('Categories.CategoryID'), nullable=False)

    def __repr__(self):
        return f"Subcategory('{self.SubcategoryName}')"


class FoodItem(db.Model):
    __tablename__ = 'FoodItems'

    FoodItemID = db.Column(db.Integer, primary_key=True)
    FoodName = db.Column(db.String(50), nullable=False)
    Description = db.Column(db.String(200), nullable=False)
    Ingredients = db.Column(db.String(200), nullable=False)
    Price = db.Column(db.Float, nullable=False)
    ImageFilename = db.Column(db.String(100), nullable=True)
    CategoryID = db.Column(db.Integer, db.ForeignKey('Categories.CategoryID'), nullable=False)

    def __repr__(self):
        return f"FoodItem('{self.FoodName}', '{self.Price}')"


class Ingredient(db.Model):
    __tablename__ = 'Ingredients'

    IngredientID = db.Column(db.Integer, primary_key=True)
    IngredientName = db.Column(db.String(50), nullable=False)

    def __repr__(self):
        return f"Ingredient('{self.IngredientName}')"


class FoodItemPromotion(db.Model):
    __tablename__ = 'FoodItemPromotions'

    FoodItemPromotionID = db.Column(db.Integer, primary_key=True)
    FoodItemID = db.Column(db.Integer, db.ForeignKey('FoodItems.FoodItemID'), nullable=False)
    PromotionID = db.Column(db.Integer, db.ForeignKey('Promotions.PromotionID'), nullable=False)

    def __repr__(self):
        return f"FoodItemPromotion('{self.FoodItemID}', '{self.PromotionID}')"


class Promotion(db.Model):
    __tablename__ = 'Promotions'

    PromotionID = db.Column(db.Integer, primary_key=True)
    PromotionName = db.Column(db.String(50), nullable=False)
    Discount = db.Column(db.Float, nullable=False)  # Assume discount is a percentage

    def __repr__(self):
        return f"Promotion('{self.PromotionName}', '{self.Discount}')"
