from flask import render_template, flash
from app import app
from app.models.models import FoodItem
from sqlalchemy.exc import OperationalError, ProgrammingError

@app.route('/')
def index():
    return "Hello, World!"

@app.route('/menu')
def menu():
    items = []
    try:
        items = FoodItem.query.all()  # Use FoodItem model
        app.logger.info(f"Retrieved items: {items}")
    except ProgrammingError as e:
        app.logger.error(f"Database table issue: {e}")
        flash("Database table issue. Unable to retrieve menu items at this time.", "danger")
    except OperationalError as e:
        app.logger.error(f"Database connection issue: {e}")
        flash("Database connection issue. Unable to retrieve menu items at this time.", "danger")
    return render_template('menu.html', items=items)
