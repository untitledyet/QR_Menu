from flask import render_template, flash, request
from app import app
from app.models.models import FoodItem, Category, Promotion
from sqlalchemy.exc import OperationalError, ProgrammingError


@app.route('/')
def index():
    categories = []
    promotions = []
    popular_dishes = []
    new_dishes = []
    filters = request.args.get('filters')

    try:
        categories = Category.query.all()
        promotions = Promotion.query.all()
        popular_dishes = FoodItem.query.order_by(FoodItem.FoodItemID.desc()).limit(
            5).all()  # Example to fetch new dishes
        new_dishes = FoodItem.query.order_by(FoodItem.FoodItemID.desc()).limit(5).all()  # Example to fetch new dishes

        if filters:
            # Add filtering logic here
            pass

        app.logger.info(f"Retrieved categories: {categories}")
        app.logger.info(f"Retrieved promotions: {promotions}")
        app.logger.info(f"Retrieved popular dishes: {popular_dishes}")
        app.logger.info(f"Retrieved new dishes: {new_dishes}")
    except ProgrammingError as e:
        app.logger.error(f"Database table issue: {e}")
        flash("Database table issue. Unable to retrieve items at this time.", "danger")
    except OperationalError as e:
        app.logger.error(f"Database connection issue: {e}")
        flash("Database connection issue. Unable to retrieve items at this time.", "danger")

    return render_template('home.html', categories=categories, promotions=promotions, popular_dishes=popular_dishes,
                           new_dishes=new_dishes)


@app.route('/menu')
def menu():
    items = []
    try:
        items = FoodItem.query.all()
        app.logger.info(f"Retrieved items: {items}")
    except ProgrammingError as e:
        app.logger.error(f"Database table issue: {e}")
        flash("Database table issue. Unable to retrieve menu items at this time.", "danger")
    except OperationalError as e:
        app.logger.error(f"Database connection issue: {e}")
        flash("Database connection issue. Unable to retrieve menu items at this time.", "danger")

    return render_template('menu.html', items=items)
