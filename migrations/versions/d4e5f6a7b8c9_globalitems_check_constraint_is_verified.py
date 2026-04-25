"""GlobalItems: add CHECK constraint — is_verified requires all fields filled

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-25 15:00:00.000000

"""
from alembic import op

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE "GlobalItems" ADD CONSTRAINT chk_verified_fields CHECK (
            is_verified = FALSE OR (
                name_ge        IS NOT NULL AND name_ge        <> '' AND
                ingredients_ge IS NOT NULL AND ingredients_ge <> '' AND
                description_ge IS NOT NULL AND description_ge <> '' AND
                name_en        IS NOT NULL AND name_en        <> '' AND
                ingredients_en IS NOT NULL AND ingredients_en <> '' AND
                description_en IS NOT NULL AND description_en <> '' AND
                image_filename IS NOT NULL AND image_filename <> ''
            )
        )
    """)


def downgrade():
    op.execute('ALTER TABLE "GlobalItems" DROP CONSTRAINT chk_verified_fields')
