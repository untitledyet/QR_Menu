"""initial schema

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-04-25 00:36:06.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Schema already exists in production — this revision is a baseline marker.
    # All tables were created via the legacy manage.py migration system.
    # Future schema changes will be generated with: flask db migrate
    pass


def downgrade():
    pass
