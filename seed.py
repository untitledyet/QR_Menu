from app import create_app, db
from app.models import Category, Subcategory, FoodItem, Promotion, Venue, AdminUser
from datetime import date, datetime

app = create_app()

with app.app_context():
    db.create_all()

    # Only seed if database is empty (idempotent for Railway deploys)
    if Venue.query.first():
        print("Database already seeded, skipping.")
        exit(0)

    # === Venues (create first so categories can reference them) ===
    venues_data = [
        Venue(id=1, name='Demo Restaurant', slug='demo', plan='premium', is_active=True),
        Venue(id=2, name='Valhalla', slug='valhalla', plan='free', is_active=True),
        Venue(id=3, name='Savane', slug='savane', plan='basic', is_active=True),
    ]
    db.session.add_all(venues_data)
    db.session.commit()

    # === Categories (Demo Restaurant only) ===
    categories = [
        Category(CategoryID=1, CategoryName='Burgers', Description='Juicy handcrafted burgers', CategoryIcon='burger.jpg', venue_id=1),
        Category(CategoryID=2, CategoryName='Pizza', Description='Wood-fired pizzas', CategoryIcon='pizza.jpg', venue_id=1),
        Category(CategoryID=3, CategoryName='Salads', Description='Fresh healthy salads', CategoryIcon='salad.jpg', venue_id=1),
        Category(CategoryID=4, CategoryName='Appetizers', Description='Tasty starters', CategoryIcon='appetaizer.jpg', venue_id=1),
        Category(CategoryID=5, CategoryName='Desserts', Description='Sweet treats', CategoryIcon='dessert.jpg', venue_id=1),
        Category(CategoryID=6, CategoryName='Drinks', Description='Refreshing beverages', CategoryIcon='drinks.jpg', venue_id=1),
        Category(CategoryID=7, CategoryName='Asian', Description='Asian cuisine favorites', CategoryIcon='asian.jpg', venue_id=1),
    ]
    db.session.add_all(categories)
    db.session.commit()

    # === Subcategories ===
    subcategories = [
        Subcategory(SubcategoryID=1, SubcategoryName='Classic Burgers', CategoryID=1),
        Subcategory(SubcategoryID=2, SubcategoryName='Special Burgers', CategoryID=1),
        Subcategory(SubcategoryID=3, SubcategoryName='Traditional Pizza', CategoryID=2),
        Subcategory(SubcategoryID=4, SubcategoryName='Specialty Pizza', CategoryID=2),
        Subcategory(SubcategoryID=5, SubcategoryName='Green Salads', CategoryID=3),
        Subcategory(SubcategoryID=6, SubcategoryName='Composed Salads', CategoryID=3),
        Subcategory(SubcategoryID=7, SubcategoryName='Hot Appetizers', CategoryID=4),
        Subcategory(SubcategoryID=8, SubcategoryName='Cold Appetizers', CategoryID=4),
        Subcategory(SubcategoryID=9, SubcategoryName='Cakes', CategoryID=5),
        Subcategory(SubcategoryID=10, SubcategoryName='Frozen', CategoryID=5),
        Subcategory(SubcategoryID=11, SubcategoryName='Hot Drinks', CategoryID=6),
        Subcategory(SubcategoryID=12, SubcategoryName='Cold Drinks', CategoryID=6),
        Subcategory(SubcategoryID=13, SubcategoryName='Noodles & Rice', CategoryID=7),
        Subcategory(SubcategoryID=14, SubcategoryName='Sushi & Dumplings', CategoryID=7),
    ]
    db.session.add_all(subcategories)
    db.session.commit()

    # === Food Items ===
    food_items = [
        # Burgers (CategoryID=1)
        FoodItem(FoodName='Cheeseburger', Description='Classic beef patty with melted cheese', Ingredients='Beef, Cheese, Lettuce, Tomato, Onion', Price=12.99, ImageFilename='cheeseburger.jpg', CategoryID=1, SubcategoryID=1),
        FoodItem(FoodName='Bacon Burger', Description='Smoky bacon with cheddar cheese', Ingredients='Beef, Bacon, Cheddar, Lettuce, Pickles', Price=14.99, ImageFilename='bacon_burger.jpg', CategoryID=1, SubcategoryID=1),
        FoodItem(FoodName='Chicken Burger', Description='Crispy chicken fillet burger', Ingredients='Chicken, Lettuce, Mayo, Tomato', Price=11.99, ImageFilename='chicken_burger.jpg', CategoryID=1, SubcategoryID=1),
        FoodItem(FoodName='Veggie Burger', Description='Plant-based patty with fresh veggies', Ingredients='Plant Patty, Avocado, Lettuce, Tomato', Price=10.99, ImageFilename='veggie_burger.jpg', CategoryID=1, SubcategoryID=2),
        FoodItem(FoodName='BBQ Burger', Description='BBQ sauce glazed burger', Ingredients='Beef, BBQ Sauce, Onion Rings, Jalapeños', Price=15.49, ImageFilename='bbq_burger.jpg', CategoryID=1, SubcategoryID=2),

        # Pizza (CategoryID=2)
        FoodItem(FoodName='Margherita Pizza', Description='Classic tomato and mozzarella', Ingredients='Dough, Tomato Sauce, Mozzarella, Basil', Price=10.99, ImageFilename='margherita_pizza.jpg', CategoryID=2, SubcategoryID=3),
        FoodItem(FoodName='Pepperoni Pizza', Description='Loaded with spicy pepperoni', Ingredients='Dough, Tomato Sauce, Mozzarella, Pepperoni', Price=12.99, ImageFilename='pepperoni_pizza.jpg', CategoryID=2, SubcategoryID=3),
        FoodItem(FoodName='Hawaiian Pizza', Description='Ham and pineapple combo', Ingredients='Dough, Tomato Sauce, Mozzarella, Ham, Pineapple', Price=13.49, ImageFilename='hawaiian_pizza.jpg', CategoryID=2, SubcategoryID=4),
        FoodItem(FoodName='BBQ Chicken Pizza', Description='BBQ chicken with red onions', Ingredients='Dough, BBQ Sauce, Chicken, Red Onion, Mozzarella', Price=14.99, ImageFilename='bbq_chicken_pizza.jpg', CategoryID=2, SubcategoryID=4),
        FoodItem(FoodName='Veggie Pizza', Description='Garden fresh vegetable pizza', Ingredients='Dough, Tomato Sauce, Bell Peppers, Mushrooms, Olives', Price=11.99, ImageFilename='veggie_pizza.jpg', CategoryID=2, SubcategoryID=4),

        # Salads (CategoryID=3)
        FoodItem(FoodName='Caesar Salad', Description='Romaine with parmesan and croutons', Ingredients='Romaine, Parmesan, Croutons, Caesar Dressing', Price=9.99, ImageFilename='caesar_salad.jpg', CategoryID=3, SubcategoryID=5),
        FoodItem(FoodName='Garden Salad', Description='Mixed greens with vinaigrette', Ingredients='Mixed Greens, Tomato, Cucumber, Carrot', Price=7.99, ImageFilename='garden_salad.jpg', CategoryID=3, SubcategoryID=5),
        FoodItem(FoodName='Greek Salad', Description='Mediterranean style with feta', Ingredients='Tomato, Cucumber, Olives, Feta, Red Onion', Price=9.49, ImageFilename='greek_salad.jpg', CategoryID=3, SubcategoryID=5),
        FoodItem(FoodName='Caprese Salad', Description='Fresh mozzarella with tomatoes', Ingredients='Mozzarella, Tomato, Basil, Balsamic', Price=10.49, ImageFilename='caprese_salad.jpg', CategoryID=3, SubcategoryID=6),
        FoodItem(FoodName='Cobb Salad', Description='Loaded salad with chicken and egg', Ingredients='Chicken, Egg, Bacon, Avocado, Blue Cheese', Price=12.99, ImageFilename='cobb_salad.jpg', CategoryID=3, SubcategoryID=6),

        # Appetizers (CategoryID=4)
        FoodItem(FoodName='Chicken Wings', Description='Crispy wings with hot sauce', Ingredients='Chicken Wings, Hot Sauce, Celery', Price=11.99, ImageFilename='chicken_wings.jpg', CategoryID=4, SubcategoryID=7),
        FoodItem(FoodName='Mozzarella Sticks', Description='Fried mozzarella with marinara', Ingredients='Mozzarella, Breadcrumbs, Marinara Sauce', Price=8.99, ImageFilename='mozzarella_sticks.jpg', CategoryID=4, SubcategoryID=7),
        FoodItem(FoodName='Garlic Bread', Description='Toasted bread with garlic butter', Ingredients='Bread, Garlic, Butter, Parsley', Price=5.99, ImageFilename='garlic_bread.jpg', CategoryID=4, SubcategoryID=7),
        FoodItem(FoodName='Stuffed Mushrooms', Description='Mushrooms filled with cheese', Ingredients='Mushrooms, Cream Cheese, Herbs', Price=9.49, ImageFilename='stuffed_mushrooms.jpg', CategoryID=4, SubcategoryID=7),
        FoodItem(FoodName='Bruschetta', Description='Toasted bread with tomato topping', Ingredients='Bread, Tomato, Basil, Garlic, Olive Oil', Price=7.99, ImageFilename='bruschetta.jpg', CategoryID=4, SubcategoryID=8),
        FoodItem(FoodName='Spring Rolls', Description='Crispy vegetable spring rolls', Ingredients='Rice Paper, Vegetables, Sweet Chili Sauce', Price=8.49, ImageFilename='spring_rolls.jpg', CategoryID=4, SubcategoryID=8),
    ]
    db.session.add_all(food_items)
    db.session.commit()

    food_items_2 = [
        # Desserts (CategoryID=5)
        FoodItem(FoodName='Chocolate Cake', Description='Rich dark chocolate layer cake', Ingredients='Chocolate, Flour, Eggs, Butter, Sugar', Price=8.99, ImageFilename='chocolate_cake.jpg', CategoryID=5, SubcategoryID=9),
        FoodItem(FoodName='Cheesecake', Description='Creamy New York style cheesecake', Ingredients='Cream Cheese, Graham Cracker, Sugar, Eggs', Price=9.49, ImageFilename='cheesecake.jpg', CategoryID=5, SubcategoryID=9),
        FoodItem(FoodName='Apple Pie', Description='Warm apple pie with cinnamon', Ingredients='Apples, Flour, Butter, Cinnamon, Sugar', Price=7.99, ImageFilename='apple_pie.jpg', CategoryID=5, SubcategoryID=9),
        FoodItem(FoodName='Brownies', Description='Fudgy chocolate brownies', Ingredients='Chocolate, Butter, Sugar, Eggs, Flour', Price=6.99, ImageFilename='brownies.jpg', CategoryID=5, SubcategoryID=9),
        FoodItem(FoodName='Vanilla Ice Cream', Description='Classic vanilla bean ice cream', Ingredients='Cream, Vanilla, Sugar, Milk', Price=5.49, ImageFilename='vanilla_ice_cream.jpg', CategoryID=5, SubcategoryID=10),

        # Drinks (CategoryID=6)
        FoodItem(FoodName='Coffee', Description='Freshly brewed arabica coffee', Ingredients='Arabica Coffee Beans, Water', Price=3.99, ImageFilename='coffee.jpg', CategoryID=6, SubcategoryID=11),
        FoodItem(FoodName='Lemonade', Description='Fresh squeezed lemonade', Ingredients='Lemon, Sugar, Water, Mint', Price=4.49, ImageFilename='lemonade.jpg', CategoryID=6, SubcategoryID=12),
        FoodItem(FoodName='Iced Tea', Description='Chilled black tea with lemon', Ingredients='Black Tea, Lemon, Sugar, Ice', Price=3.99, ImageFilename='iced_tea.jpg', CategoryID=6, SubcategoryID=12),
        FoodItem(FoodName='Mango Smoothie', Description='Tropical mango blend', Ingredients='Mango, Yogurt, Honey, Ice', Price=5.99, ImageFilename='mango_smoothie.jpg', CategoryID=6, SubcategoryID=12),
        FoodItem(FoodName='Chocolate Milkshake', Description='Thick chocolate milkshake', Ingredients='Chocolate Ice Cream, Milk, Whipped Cream', Price=6.49, ImageFilename='chocolate_milkshake.jpg', CategoryID=6, SubcategoryID=12),

        # Asian (CategoryID=7)
        FoodItem(FoodName='Pad Thai', Description='Stir-fried rice noodles', Ingredients='Rice Noodles, Shrimp, Peanuts, Bean Sprouts', Price=13.99, ImageFilename='pad_thai.jpg', CategoryID=7, SubcategoryID=13),
        FoodItem(FoodName='General Tso Chicken', Description='Sweet and spicy fried chicken', Ingredients='Chicken, Soy Sauce, Ginger, Garlic, Chili', Price=14.49, ImageFilename='general_tsos_chicken.jpg', CategoryID=7, SubcategoryID=13),
        FoodItem(FoodName='Sushi', Description='Assorted fresh sushi platter', Ingredients='Rice, Salmon, Tuna, Nori, Wasabi', Price=16.99, ImageFilename='sushi.jpg', CategoryID=7, SubcategoryID=14),
        FoodItem(FoodName='Dumplings', Description='Steamed pork dumplings', Ingredients='Pork, Ginger, Cabbage, Soy Sauce', Price=10.99, ImageFilename='dumplings.jpg', CategoryID=7, SubcategoryID=14),
        FoodItem(FoodName='Miso Soup', Description='Traditional Japanese miso soup', Ingredients='Miso Paste, Tofu, Seaweed, Green Onion', Price=4.99, ImageFilename='miso_soup.jpg', CategoryID=7, SubcategoryID=14),
        FoodItem(FoodName='Grilled Chicken', Description='Herb marinated grilled chicken', Ingredients='Chicken, Herbs, Olive Oil, Lemon', Price=13.49, ImageFilename='grilled_chicken.jpg', CategoryID=7, SubcategoryID=13),
        FoodItem(FoodName='Spaghetti Carbonara', Description='Creamy pasta with bacon', Ingredients='Spaghetti, Bacon, Egg, Parmesan, Cream', Price=12.99, ImageFilename='spaghetti_carbonara.jpg', CategoryID=7, SubcategoryID=13),
    ]
    db.session.add_all(food_items_2)
    db.session.commit()

    # === Promotions ===
    promotions = [
        Promotion(PromotionID=1, PromotionName='Free Cocktail', Description='Get a free cocktail with any main course order', Discount=0, StartDate=date(2025, 1, 1), EndDate=date(2026, 12, 31), BackgroundImage='Cocktail_Gift.jpg', venue_id=1),
        Promotion(PromotionID=2, PromotionName='QR Menu Sale', Description='20% off when you order through QR menu', Discount=20, StartDate=date(2025, 1, 1), EndDate=date(2026, 12, 31), BackgroundImage='QR_Sale.jpg', venue_id=1),
        Promotion(PromotionID=3, PromotionName='Happy Hour', Description='Buy 1 dessert, get 1 free every Friday', Discount=50, StartDate=date(2025, 3, 1), EndDate=date(2026, 12, 31), BackgroundImage='Happy_Hour.jpg', venue_id=1),
    ]
    db.session.add_all(promotions)
    db.session.commit()

    print("Database seeded successfully!")
    print(f"  Categories: {Category.query.count()}")
    print(f"  Subcategories: {Subcategory.query.count()}")
    print(f"  Food Items: {FoodItem.query.count()}")
    print(f"  Promotions: {Promotion.query.count()}")

    # === Admin Users ===
    super_admin = AdminUser(username='superadmin', role='super')
    super_admin.set_password('1234')
    db.session.add(super_admin)

    admin1 = AdminUser(username='admin', role='venue', venue_id=1)
    admin1.set_password('admin')
    db.session.add(admin1)

    admin2 = AdminUser(username='valhalla', role='venue', venue_id=2)
    admin2.set_password('valhalla')
    db.session.add(admin2)

    admin3 = AdminUser(username='savane', role='venue', venue_id=3)
    admin3.set_password('savane')
    db.session.add(admin3)

    db.session.commit()

    print(f"  Venues: {Venue.query.count()}")
    print(f"  Admins: superadmin/1234, admin/admin, valhalla/valhalla, savane/savane")
