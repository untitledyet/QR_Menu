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

        # Fix sms_code_hash column type if it was created/renamed as VARCHAR(6) or similar short type
        from sqlalchemy import inspect as sa_inspect
        sms_col_info = next((c for c in sa_inspect(db.engine).get_columns('AdminUsers')
                             if c['name'] == 'sms_code_hash'), None)
        if sms_col_info:
            col_type_str = str(sms_col_info['type'])
            # Check if length is too short (anything under 200 chars)
            if hasattr(sms_col_info['type'], 'length') and sms_col_info['type'].length < 200:
                with db.engine.connect() as conn:
                    conn.execute(text(
                        'ALTER TABLE "AdminUsers" ALTER COLUMN sms_code_hash TYPE VARCHAR(256)'
                    ))
                    conn.commit()
                print('Migration: widened sms_code_hash to VARCHAR(256)')

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

        if 'two_fa_enabled' not in admin_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "AdminUsers" ADD COLUMN two_fa_enabled BOOLEAN NOT NULL DEFAULT TRUE'))
                conn.commit()
            print('Migration: added two_fa_enabled to AdminUsers')

        # --- PhoneOtps table migrations ---
        if 'PhoneOtps' in table_names:
            otp_cols = [c['name'] for c in insp.get_columns('PhoneOtps')]
            if 'ip' not in otp_cols:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE "PhoneOtps" ADD COLUMN ip VARCHAR(45)'))
                    conn.commit()
                print('Migration: added ip to PhoneOtps')

        # --- VenueGroups table ---
        if 'VenueGroups' not in table_names:
            with db.engine.connect() as conn:
                conn.execute(text('''
                    CREATE TABLE "VenueGroups" (
                        id SERIAL PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        owner_venue_id INTEGER NOT NULL REFERENCES "Venues"(id),
                        allow_price_override BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                '''))
                conn.commit()
            print('Migration: created VenueGroups table')

        # --- Venues.group_id ---
        venue_cols = [c['name'] for c in insp.get_columns('Venues')]
        if 'group_id' not in venue_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "Venues" ADD COLUMN group_id INTEGER REFERENCES "VenueGroups"(id)'))
                conn.commit()
            print('Migration: added group_id to Venues')

        # --- VenueGroupInvites table ---
        if 'VenueGroupInvites' not in table_names:
            with db.engine.connect() as conn:
                conn.execute(text('''
                    CREATE TABLE "VenueGroupInvites" (
                        id SERIAL PRIMARY KEY,
                        group_id INTEGER NOT NULL REFERENCES "VenueGroups"(id),
                        invite_code VARCHAR(20) UNIQUE NOT NULL,
                        invited_by INTEGER NOT NULL REFERENCES "AdminUsers"(id),
                        target_venue_id INTEGER REFERENCES "Venues"(id),
                        status VARCHAR(20) NOT NULL DEFAULT \'pending\',
                        expires_at TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                '''))
                conn.commit()
            print('Migration: created VenueGroupInvites table')

        # --- Categories.group_id ---
        cat_cols = [c['name'] for c in insp.get_columns('Categories')]
        if 'group_id' not in cat_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "Categories" ADD COLUMN group_id INTEGER REFERENCES "VenueGroups"(id)'))
                conn.commit()
            print('Migration: added group_id to Categories')

        # --- VenueItemPriceOverrides table ---
        if 'VenueItemPriceOverrides' not in table_names:
            with db.engine.connect() as conn:
                conn.execute(text('''
                    CREATE TABLE "VenueItemPriceOverrides" (
                        id SERIAL PRIMARY KEY,
                        venue_id INTEGER NOT NULL REFERENCES "Venues"(id),
                        food_item_id INTEGER NOT NULL REFERENCES "FoodItems"("FoodItemID"),
                        price FLOAT NOT NULL,
                        CONSTRAINT uq_venue_item_price UNIQUE (venue_id, food_item_id)
                    )
                '''))
                conn.commit()
            print('Migration: created VenueItemPriceOverrides table')

        # --- Multilingual _en columns ---
        cat_cols = [c['name'] for c in insp.get_columns('Categories')]
        for col, typ in [('CategoryName_en', 'VARCHAR(50)'), ('Description_en', 'VARCHAR(200)')]:
            if col not in cat_cols:
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE "Categories" ADD COLUMN "{col}" {typ}'))
                    conn.commit()
                print(f'Migration: added {col} to Categories')

        sub_cols = [c['name'] for c in insp.get_columns('Subcategories')]
        if 'SubcategoryName_en' not in sub_cols:
            with db.engine.connect() as conn:
                conn.execute(text('ALTER TABLE "Subcategories" ADD COLUMN "SubcategoryName_en" VARCHAR(50)'))
                conn.commit()
            print('Migration: added SubcategoryName_en to Subcategories')

        food_cols = [c['name'] for c in insp.get_columns('FoodItems')]
        for col, typ in [('FoodName_en', 'VARCHAR(50)'), ('Description_en', 'VARCHAR(200)'), ('Ingredients_en', 'VARCHAR(200)')]:
            if col not in food_cols:
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE "FoodItems" ADD COLUMN "{col}" {typ}'))
                    conn.commit()
                print(f'Migration: added {col} to FoodItems')

        if 'GlobalCategories' in table_names:
            gcat_cols = [c['name'] for c in insp.get_columns('GlobalCategories')]
            for col, typ in [('name_en', 'VARCHAR(100)'), ('description_en', 'VARCHAR(300)')]:
                if col not in gcat_cols:
                    with db.engine.connect() as conn:
                        conn.execute(text(f'ALTER TABLE "GlobalCategories" ADD COLUMN "{col}" {typ}'))
                        conn.commit()
                    print(f'Migration: added {col} to GlobalCategories')

        if 'GlobalSubcategories' in table_names:
            gsub_cols = [c['name'] for c in insp.get_columns('GlobalSubcategories')]
            if 'name_en' not in gsub_cols:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE "GlobalSubcategories" ADD COLUMN "name_en" VARCHAR(100)'))
                    conn.commit()
                print('Migration: added name_en to GlobalSubcategories')

        if 'GlobalItems' in table_names:
            gitem_cols = [c['name'] for c in insp.get_columns('GlobalItems')]
            for col, typ in [('name_en', 'VARCHAR(100)'), ('description_en', 'VARCHAR(500)'), ('ingredients_en', 'VARCHAR(500)')]:
                if col not in gitem_cols:
                    with db.engine.connect() as conn:
                        conn.execute(text(f'ALTER TABLE "GlobalItems" ADD COLUMN "{col}" {typ}'))
                        conn.commit()
                    print(f'Migration: added {col} to GlobalItems')

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
