from app import create_app, db
from sqlalchemy import inspect, text

app = create_app()

with app.app_context():
    db.create_all()

    # Ensure total_tables column exists (migration for existing DBs)
    try:
        insp = inspect(db.engine)
        cols = [c['name'] for c in insp.get_columns('Venues')]
        if 'total_tables' not in cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "Venues" ADD COLUMN total_tables INTEGER NOT NULL DEFAULT 0'))
                conn.commit()
            print('Migration: added total_tables to Venues')
        else:
            print('Migration: total_tables already exists')
    except Exception as e:
        print(f'Migration error: {e}')

if __name__ == '__main__':
    app.run()
