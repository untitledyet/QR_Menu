from app import create_app, db
from sqlalchemy import inspect, text

app = create_app()


def run_migrations():
    """Run all pending column migrations. Safe to run multiple times."""
    with app.app_context():
        db.create_all()

        insp = inspect(db.engine)

        # --- Venues table migrations ---
        venue_cols = [c['name'] for c in insp.get_columns('Venues')]

        if 'total_tables' not in venue_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "Venues" ADD COLUMN total_tables INTEGER NOT NULL DEFAULT 0'))
                conn.commit()
            print('Migration: added total_tables to Venues')

        if 'venue_code' not in venue_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "Venues" ADD COLUMN venue_code VARCHAR(12) UNIQUE'))
                conn.commit()
            print('Migration: added venue_code to Venues')
            # Backfill existing venues
            _backfill_venue_codes()

        # --- AdminUsers table migrations ---
        admin_cols = [c['name'] for c in insp.get_columns('AdminUsers')]

        if 'reset_token' not in admin_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "AdminUsers" ADD COLUMN reset_token VARCHAR(64)'))
                conn.execute(text('ALTER TABLE "AdminUsers" ADD COLUMN reset_token_expires DATETIME'))
                conn.commit()
            print('Migration: added reset_token fields to AdminUsers')

        print('Migrations complete.')


def _backfill_venue_codes():
    """Assign venue_code to existing venues that don't have one."""
    from app.models import Venue, _generate_venue_code
    with app.app_context():
        venues = Venue.query.filter_by(venue_code=None).all()
        for venue in venues:
            while True:
                code = _generate_venue_code()
                if not Venue.query.filter_by(venue_code=code).first():
                    break
            venue.venue_code = code
        db.session.commit()
        if venues:
            print(f'Backfilled venue_code for {len(venues)} venues.')


if __name__ == '__main__':
    run_migrations()
    app.run()
