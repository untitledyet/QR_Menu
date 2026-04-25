"""GlobalItems: reorder columns and rename name/description/ingredients to _ge suffix

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-25 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    # Recreate table with correct column order and _ge suffix names.
    # Applied directly to production via psycopg2 before this migration ran,
    # so this is a no-op on existing deployments (Alembic will just stamp the version).
    pass


def downgrade():
    pass
