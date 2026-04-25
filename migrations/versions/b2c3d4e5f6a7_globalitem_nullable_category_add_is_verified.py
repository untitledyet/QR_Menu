"""GlobalItem: category_id nullable, add is_verified

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('GlobalItems', 'category_id', nullable=True)
    op.add_column('GlobalItems', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'))


def downgrade():
    op.drop_column('GlobalItems', 'is_verified')
    op.alter_column('GlobalItems', 'category_id', nullable=False)
