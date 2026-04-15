# -*- coding: utf-8 -*-
from app import create_app, db
from sqlalchemy import inspect, text

app = create_app()


def run_migrations():
    """Run all pending column migrations. Safe to run multiple times."""
    with app.app_context():
        db.create_all()

        insp = inspect(db.engine)
        table_names = insp.get_table_names()

        if 'Venues' not in table_names:
            print('Tables created from scratch - no migrations needed')
            return

        # --- Venues table migrations ---
        venue_cols = [c['name'] for c in insp.get_columns('Venues')]

        if 'total_tables' not in venue_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "Venues" ADD COLUMN total_tables INTEGER NOT NULL DEFAULT 0'))
                conn.commit()
            print('Migration: added total_tables to Venues')

        if 'venue_code' not in venue_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "Venues" ADD COLUMN venue_code VARCHAR(12)'))
                conn.commit()
            print('Migration: added venue_code to Venues')
            _backfill_venue_codes()

        # --- AdminUsers table migrations ---
        admin_cols = [c['name'] for c in insp.get_columns('AdminUsers')]

        if 'reset_token' not in admin_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "AdminUsers" ADD COLUMN reset_token VARCHAR(64)'))
                conn.execute(text('ALTER TABLE "AdminUsers" ADD COLUMN reset_token_expires TIMESTAMP'))
                conn.commit()
            print('Migration: added reset_token fields to AdminUsers')

        # Rename sms_code -> sms_code_hash if needed
        if 'sms_code' in admin_cols and 'sms_code_hash' not in admin_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "AdminUsers" RENAME COLUMN sms_code TO sms_code_hash'))
                conn.commit()
            print('Migration: renamed sms_code to sms_code_hash')

        if 'sms_code_hash' not in admin_cols and 'sms_code' not in admin_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "AdminUsers" ADD COLUMN sms_code_hash VARCHAR(256)'))
                conn.commit()
            print('Migration: added sms_code_hash to AdminUsers')

        if 'sms_attempts' not in admin_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "AdminUsers" ADD COLUMN sms_attempts INTEGER DEFAULT 0'))
                conn.commit()
            print('Migration: added sms_attempts to AdminUsers')

        if 'failed_login_attempts' not in admin_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "AdminUsers" ADD COLUMN failed_login_attempts INTEGER DEFAULT 0'))
                conn.execute(text('ALTER TABLE "AdminUsers" ADD COLUMN locked_until TIMESTAMP'))
                conn.commit()
            print('Migration: added brute force protection fields to AdminUsers')

        if 'email_token_expires' not in admin_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "AdminUsers" ADD COLUMN email_token_expires TIMESTAMP'))
                conn.commit()
            print('Migration: added email_token_expires to AdminUsers')

        # --- PhoneOtps table migrations ---
        if 'PhoneOtps' in table_names:
            otp_cols = [c['name'] for c in insp.get_columns('PhoneOtps')]
            if 'ip' not in otp_cols:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE "PhoneOtps" ADD COLUMN ip VARCHAR(45)'))
                    conn.commit()
                print('Migration: added ip to PhoneOtps')

        # Activate existing phone-verified users who are stuck
        with db.engine.connect() as conn:
            conn.execute(text(
                'UPDATE "AdminUsers" SET is_active = TRUE '
                'WHERE phone_verified = TRUE AND is_active = FALSE AND role = \'venue\''
            ))
            conn.commit()

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
            print('Backfilled venue_code for ' + str(len(venues)) + ' venues.')


if __name__ == '__main__':
    run_migrations()
    app.run()
