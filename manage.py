from app import create_app, db

app = create_app()

with app.app_context():
    db.create_all()  # ეს შექმნის მონაცემთა ბაზის სქემას, თუ არ არის

if __name__ == '__main__':
    app.run()
